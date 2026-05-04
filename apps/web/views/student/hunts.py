"""Student-facing Hunt (Goal) views.

- `hunt_list_view`     — all Hunts grouped by status.
- `hunt_new_view`      — create a Hunt; LLM-decomposes into Tasks on save.
- `hunt_detail_view`   — dungeon-map view of the Hunt's Task chain.
- `hunt_task_complete_view` — mark a task complete; award XP; recompute progress.
"""

import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import role_required
from apps.service.models import Goal, Subject, Task, XPLedger
from apps.service.services.hunts import (
    decompose_goal,
    ensure_quiz_questions,
    grade_quiz,
)
from apps.service.services.missions import mark_item_completed_for_event
from apps.service.services.xp import award_xp

logger = logging.getLogger(__name__)


@login_required
@role_required(['student'])
def hunt_list_view(request):
    qs = (
        Goal.objects
        .filter(student=request.user)
        .select_related('subject')
        .prefetch_related('tasks')
        .order_by('-created_at')
    )
    # Expire any overdue active hunts before rendering
    today = timezone.localdate()
    for g in list(qs.filter(status=Goal.STATUS_ACTIVE, target_date__lt=today)):
        g.status = Goal.STATUS_EXPIRED
        g.save(update_fields=['status', 'updated_at'])

    groups = {
        'active': [g for g in qs if g.status == Goal.STATUS_ACTIVE],
        'completed': [g for g in qs if g.status == Goal.STATUS_COMPLETED],
        'expired': [g for g in qs if g.status in (Goal.STATUS_EXPIRED, Goal.STATUS_ABANDONED)],
    }

    profile = getattr(request.user, 'profile', None)
    return render(request, 'student/hunts/list.html', {
        'user': request.user,
        'profile': profile,
        'groups': groups,
        'group_counts': {k: len(v) for k, v in groups.items()},
        'active_page': 'hunts',
    })


@login_required
@role_required(['student'])
def hunt_new_view(request):
    subjects = list(Subject.objects.filter(tenant=request.user.tenant, is_active=True))

    default_target = (timezone.localdate() + timedelta(days=14)).isoformat()

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()[:200]
        description = request.POST.get('description', '').strip()[:2000]
        subject_id = request.POST.get('subject', '').strip()
        target_date = request.POST.get('target_date', '').strip()

        errors = []
        if not title:
            errors.append('Give your Hunt a title.')
        if not target_date:
            errors.append('Pick a target date.')
        try:
            parsed_target = timezone.datetime.strptime(target_date, '%Y-%m-%d').date() \
                if target_date else None
        except ValueError:
            errors.append('Target date must be YYYY-MM-DD.')
            parsed_target = None

        if parsed_target and parsed_target <= timezone.localdate():
            errors.append('Target date must be in the future.')

        subject = None
        if subject_id:
            try:
                subject = Subject.objects.get(
                    pk=int(subject_id), tenant=request.user.tenant,
                )
            except (Subject.DoesNotExist, ValueError):
                errors.append('Unknown subject.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'student/hunts/new.html', {
                'user': request.user,
                'profile': getattr(request.user, 'profile', None),
                'subjects': subjects,
                'default_target': default_target,
                'prior': {
                    'title': title, 'description': description,
                    'subject_id': subject_id, 'target_date': target_date,
                },
                'active_page': 'hunts',
            })

        goal = Goal.objects.create(
            student=request.user,
            title=title,
            description=description,
            subject=subject,
            target_date=parsed_target,
            status=Goal.STATUS_ACTIVE,
        )

        try:
            decompose_goal(goal)
        except Exception as exc:  # pragma: no cover — decomposer has internal fallback
            logger.warning('decompose_goal failed for %s: %s', goal.id, exc)
            goal.decomposition_error = str(exc)[:2000]
            goal.save(update_fields=['decomposition_error', 'updated_at'])

        messages.success(request, f'Hunt "{goal.title}" deployed. Plan ready.')
        return redirect('student:hunt_detail', pk=goal.id)

    return render(request, 'student/hunts/new.html', {
        'user': request.user,
        'profile': getattr(request.user, 'profile', None),
        'subjects': subjects,
        'default_target': default_target,
        'prior': {},
        'active_page': 'hunts',
    })


def _student_hunt_qs(user):
    return Goal.objects.filter(student=user).select_related('subject').prefetch_related('tasks')


@login_required
@role_required(['student'])
def hunt_detail_view(request, pk):
    goal = get_object_or_404(_student_hunt_qs(request.user), pk=pk)
    tasks = list(goal.tasks.order_by('order', 'id'))

    # Determine the "current" task — first incomplete
    current_index = None
    for i, t in enumerate(tasks):
        if not t.is_completed:
            current_index = i
            break

    profile = getattr(request.user, 'profile', None)
    return render(request, 'student/hunts/detail.html', {
        'user': request.user,
        'profile': profile,
        'goal': goal,
        'tasks': tasks,
        'current_index': current_index,
        'active_page': 'hunts',
    })


@login_required
@role_required(['student'])
def hunt_task_quiz_view(request, task_pk):
    """GET: render the quiz form for a task.
    POST: grade answers, award XP + complete the task if the student passed.

    Quizzes are MCQs generated + cached on the Task; retries show the same
    questions so the per-question explanations are actually instructive.
    """
    task = get_object_or_404(
        Task.objects.select_related('goal', 'goal__subject', 'ref_node'),
        pk=task_pk,
        goal__student=request.user,
    )
    goal = task.goal

    if task.is_completed:
        messages.info(request, f'You already cleared "{task.title}".')
        return redirect('student:hunt_detail', pk=goal.id)

    if goal.status != Goal.STATUS_ACTIVE:
        messages.error(request, 'This Hunt is no longer active.')
        return redirect('student:hunt_detail', pk=goal.id)

    # Lazy-populate + cache the quiz on first render
    questions = ensure_quiz_questions(task)

    profile = getattr(request.user, 'profile', None)
    base_ctx = {
        'user': request.user,
        'profile': profile,
        'task': task,
        'goal': goal,
        'questions': questions,
        'required_count': task.required_questions(),
        'pass_threshold': task.pass_threshold_pct(),
        'active_page': 'hunts',
    }

    if request.method != 'POST':
        base_ctx.update({'show_result': False})
        return render(request, 'student/hunts/task_quiz.html', base_ctx)

    # --- POST: grade + reward ---
    responses = [
        {'qid': idx, 'selected': request.POST.get(f'q_{idx}', '').strip()}
        for idx in range(len(questions))
    ]
    grade = grade_quiz(task, responses)

    # Update best score
    if task.best_score_pct is None or grade['pct'] > task.best_score_pct:
        task.best_score_pct = grade['pct']
        task.save(update_fields=['best_score_pct', 'updated_at'])

    xp_awarded = 0
    leveled_up = False
    ranked_up = False
    goal_bonus = 0

    if grade['passed']:
        task.mark_completed()
        xp_result = award_xp(
            request.user,
            source=XPLedger.SOURCE_HUNT_TASK,
            amount=int(task.xp_reward or 0),
            description=f'Hunt task: {task.title[:140]}',
            related_object_type='hunt_task',
            related_object_id=task.id,
        )
        xp_awarded = xp_result.awarded
        leveled_up = xp_result.leveled_up
        ranked_up = xp_result.ranked_up

        # Goal-complete bonus (if this was the last task)
        goal.refresh_from_db()
        if goal.status == Goal.STATUS_COMPLETED:
            bonus = award_xp(
                request.user,
                source=XPLedger.SOURCE_HUNT_COMPLETE,
                amount=int(goal.xp_reward or 0),
                description=f'Hunt cleared: {goal.title[:140]}',
                related_object_type='hunt',
                related_object_id=goal.id,
            )
            goal_bonus = bonus.awarded
            # Second award can also level-up / rank-up
            leveled_up = leveled_up or bonus.leveled_up
            ranked_up = ranked_up or bonus.ranked_up

        # Close matching MissionItem (hunt_task) if one exists today
        try:
            mark_item_completed_for_event(request.user, 'hunt_task', task.id)
        except Exception:
            pass

    base_ctx.update({
        'show_result': True,
        'grade': grade,
        'xp_awarded': xp_awarded,
        'leveled_up': leveled_up,
        'ranked_up': ranked_up,
        'goal_bonus': goal_bonus,
    })
    return render(request, 'student/hunts/task_quiz.html', base_ctx)


@login_required
@role_required(['student'])
@require_POST
def hunt_abandon_view(request, pk):
    goal = get_object_or_404(_student_hunt_qs(request.user), pk=pk)
    if goal.status == Goal.STATUS_ACTIVE:
        goal.status = Goal.STATUS_ABANDONED
        goal.save(update_fields=['status', 'updated_at'])
        messages.info(request, f'Hunt "{goal.title}" abandoned.')
    return redirect('student:hunt_list')
