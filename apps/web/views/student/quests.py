"""Student-facing Quest (Assignment) views.

Three flows:
- `quest_list_view`  — lists published Assignments for the student's classes.
- `quest_chamber_view` + autosave + submit — the full-screen take experience.
- `quest_results_view` — per-question grading + XP awarded after submission.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import role_required
from apps.service.models import Assignment, Enrollment, Question, StudentAssignment
from apps.service.services.quests import (
    grade_student_assignment,
    save_draft_answers,
    start_attempt,
)


def _student_assignments_qs(user):
    """All published Assignments for classes the student is enrolled in.

    If the student has no Enrollment rows yet, fall back to matching by
    grade_level within the same tenant so the list isn't empty during the
    Phase A → Phase B transition.
    """
    class_ids = list(
        Enrollment.objects.filter(student=user, is_active=True)
        .values_list('class_obj_id', flat=True)
    )
    qs = (
        Assignment.objects
        .filter(
            tenant=user.tenant,
            status=Assignment.STATUS_PUBLISHED,
        )
        .select_related('subject', 'class_obj')
        .order_by('due_date')
    )
    if class_ids:
        qs = qs.filter(class_obj_id__in=class_ids)
    else:
        qs = qs.filter(class_obj__grade_level=user.grade_level)
    return qs


@login_required
@role_required(['student'])
def quest_list_view(request):
    assignments = list(_student_assignments_qs(request.user))
    sas = {
        sa.assignment_id: sa
        for sa in StudentAssignment.objects.filter(
            student=request.user, assignment__in=assignments,
        )
    }

    now = timezone.now()
    rows = []
    for a in assignments:
        sa = sas.get(a.id)
        status = sa.status if sa else StudentAssignment.STATUS_PENDING
        due_in = a.due_date - now
        if due_in.total_seconds() < 0:
            due_chip = 'Overdue'
            due_variant = 'crimson'
        elif due_in.total_seconds() < 24 * 3600:
            due_chip = 'Due today'
            due_variant = 'crimson'
        elif due_in.total_seconds() < 72 * 3600:
            due_chip = f'Due in {int(due_in.total_seconds() // 3600)}h'
            due_variant = 'gold'
        else:
            due_chip = f'Due in {due_in.days}d'
            due_variant = 'cyan'
        rows.append({
            'assignment': a,
            'status': status,
            'sa': sa,
            'due_chip': due_chip,
            'due_variant': due_variant,
        })

    tabs = {
        'active': [
            r for r in rows
            if r['status'] in (
                StudentAssignment.STATUS_PENDING,
                StudentAssignment.STATUS_IN_PROGRESS,
            )
        ],
        'submitted': [r for r in rows if r['status'] == StudentAssignment.STATUS_SUBMITTED],
        'graded': [r for r in rows if r['status'] == StudentAssignment.STATUS_GRADED],
    }

    current_tab = request.GET.get('tab', 'active')
    if current_tab not in tabs:
        current_tab = 'active'

    profile = getattr(request.user, 'profile', None)
    return render(request, 'student/quests/list.html', {
        'user': request.user,
        'profile': profile,
        'tabs': tabs,
        'current_tab': current_tab,
        'tab_counts': {name: len(items) for name, items in tabs.items()},
        'active_page': 'quests',
    })


def _fetch_assignment_for_student(user, pk) -> Assignment:
    return get_object_or_404(_student_assignments_qs(user).filter(pk=pk))


@login_required
@role_required(['student'])
def quest_chamber_view(request, pk):
    """Entry point — starts attempt if needed, renders the full-screen take view."""
    assignment = _fetch_assignment_for_student(request.user, pk)
    sa = start_attempt(request.user, assignment)

    if sa.status in (StudentAssignment.STATUS_SUBMITTED, StudentAssignment.STATUS_GRADED):
        return redirect('student:quest_results', pk=pk)

    questions = list(assignment.questions.all().order_by('order', 'id'))
    existing_answers = {
        a.question_id: a
        for a in sa.answers.select_related('question').all()
    }

    payload = []
    for q in questions:
        existing = existing_answers.get(q.id)
        payload.append({
            'id': q.id,
            'order': q.order,
            'type': q.question_type,
            'text': q.question_text,
            'marks': q.marks,
            'options': (
                q.student_visible_options()
                if q.question_type == Question.TYPE_MCQ else []
            ),
            'saved_selection': (
                existing.selected_option_key
                if (existing and q.question_type == Question.TYPE_MCQ) else ''
            ),
            'saved_text': (
                existing.answer_text
                if (existing and q.question_type != Question.TYPE_MCQ) else ''
            ),
        })

    profile = getattr(request.user, 'profile', None)
    return render(request, 'student/quests/chamber.html', {
        'user': request.user,
        'profile': profile,
        'assignment': assignment,
        'sa': sa,
        'questions_payload': payload,
        'active_page': 'quests',
    })


@login_required
@role_required(['student'])
@require_POST
def quest_save_draft_view(request, pk):
    """Autosave endpoint.

    POST JSON: {"answers": [{question_id, selected_option_key, answer_text}, ...]}
    """
    assignment = _fetch_assignment_for_student(request.user, pk)
    sa = start_attempt(request.user, assignment)
    if sa.status in (StudentAssignment.STATUS_SUBMITTED, StudentAssignment.STATUS_GRADED):
        return JsonResponse(
            {'ok': False, 'error': 'Attempt already submitted'}, status=409,
        )
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid JSON')
    answers = body.get('answers') or []
    if not isinstance(answers, list):
        return HttpResponseBadRequest('answers must be a list')
    count = save_draft_answers(sa, answers)
    return JsonResponse({'ok': True, 'saved': count})


@login_required
@role_required(['student'])
@require_POST
def quest_submit_view(request, pk):
    """Finalize + grade. Accepts JSON body or form-encoded final answers."""
    assignment = _fetch_assignment_for_student(request.user, pk)
    sa = start_attempt(request.user, assignment)
    if sa.status in (StudentAssignment.STATUS_SUBMITTED, StudentAssignment.STATUS_GRADED):
        return redirect('student:quest_results', pk=pk)

    content_type = request.content_type or ''
    final_answers = []
    if 'application/json' in content_type:
        try:
            body = json.loads(request.body or b'{}')
        except json.JSONDecodeError:
            return HttpResponseBadRequest('Invalid JSON')
        final_answers = body.get('answers') or []
    else:
        for q in assignment.questions.all():
            raw = request.POST.get(f'q_{q.id}', '')
            if q.question_type == Question.TYPE_MCQ:
                final_answers.append({
                    'question_id': q.id,
                    'selected_option_key': raw,
                })
            else:
                final_answers.append({
                    'question_id': q.id,
                    'answer_text': raw,
                })

    save_draft_answers(sa, final_answers)
    graded = grade_student_assignment(sa)

    if 'application/json' in content_type:
        return JsonResponse({
            'ok': True,
            'redirect': f'/student/quests/{assignment.id}/results/',
            'status': graded.status,
        })

    messages.success(request, 'Quest submitted.')
    return redirect('student:quest_results', pk=pk)


@login_required
@role_required(['student'])
def quest_results_view(request, pk):
    assignment = _fetch_assignment_for_student(request.user, pk)
    sa = get_object_or_404(
        StudentAssignment, student=request.user, assignment=assignment,
    )
    answers = list(
        sa.answers.select_related('question')
        .order_by('question__order', 'question_id')
    )
    decorated = []
    for a in answers:
        q = a.question
        correct_text = ''
        selected_text = ''
        if q.question_type == Question.TYPE_MCQ:
            options = q.options or []
            for opt in options:
                if isinstance(opt, dict):
                    if opt.get('key') == q.correct_answer:
                        correct_text = opt.get('text', '')
                    if opt.get('key') == a.selected_option_key:
                        selected_text = opt.get('text', '')
        decorated.append({
            'answer': a,
            'question': q,
            'correct_text': correct_text,
            'selected_text': selected_text,
        })

    profile = getattr(request.user, 'profile', None)
    return render(request, 'student/quests/results.html', {
        'user': request.user,
        'profile': profile,
        'assignment': assignment,
        'sa': sa,
        'decorated': decorated,
        'active_page': 'quests',
    })
