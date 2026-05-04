"""Teacher-facing Quest (Assignment) management.

Minimal Phase B teacher UI: create a quest from a topic, auto-generate MCQs
via the existing `QuestionGenerator` (LLM primary, stub fallback), review
the draft, edit correct answers inline if needed, and publish when ready.
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
from apps.service.models import Assignment, Class, ContentNode, Question, Subject
from apps.service.services.assessments.question_generator import QuestionGenerator

logger = logging.getLogger(__name__)


def _teacher_classes(user):
    """Classes the teacher is the homeroom teacher OR subject-teacher of."""
    from django.db.models import Q
    return (
        Class.objects
        .filter(tenant=user.tenant, is_active=True)
        .filter(
            Q(class_teacher=user) | Q(class_subjects__teacher=user)
        )
        .distinct()
        .select_related('tenant')
        .order_by('grade_level', 'section')
    )


def _teacher_assignments(user):
    """Assignments the teacher created or owns via their classes."""
    class_ids = list(_teacher_classes(user).values_list('id', flat=True))
    return (
        Assignment.objects
        .filter(tenant=user.tenant)
        .filter(class_obj_id__in=class_ids)
        .select_related('class_obj', 'subject', 'created_by')
        .prefetch_related('questions')
        .order_by('-created_at')
    )


@login_required
@role_required(['teacher', 'school_admin'])
def quest_list_view(request):
    assignments = list(_teacher_assignments(request.user))
    groups = {
        'draft': [a for a in assignments if a.status == Assignment.STATUS_DRAFT],
        'published': [a for a in assignments if a.status == Assignment.STATUS_PUBLISHED],
        'archived': [a for a in assignments if a.status == Assignment.STATUS_ARCHIVED],
    }
    return render(request, 'teacher/quests/list.html', {
        'user': request.user,
        'groups': groups,
        'counts': {k: len(v) for k, v in groups.items()},
        'active_page': 'quests',
    })


def _build_canned_mcq(topic_title: str, subject_name: str, n: int) -> list[dict]:
    """Used when the LLM is unavailable. Returns n canned MCQs tied to the topic."""
    out = []
    for i in range(n):
        out.append({
            'question': (
                f'Which of these best relates to "{topic_title}" '
                f'in {subject_name}?  (Q {i + 1})'
            ),
            'options': [
                f'A) {topic_title}',
                'B) An unrelated topic',
                'C) A different subject entirely',
                'D) None of the above',
            ],
            'correct_answer': f'A) {topic_title}',
            'explanation': f'"{topic_title}" is the correct answer.',
            'type': 'mcq',
        })
    return out


def _generate_questions(topic_title: str, subject_name: str, count: int, difficulty: str) -> list[dict]:
    """Prefer the real LLM-backed generator; fall back to canned MCQs on any error."""
    try:
        generator = QuestionGenerator()
        raw = generator.generate_questions(
            topic=topic_title,
            difficulty=difficulty,
            count=count,
            question_type='mcq',
            subject_context=subject_name,
        )
        if raw:
            return raw
    except Exception as exc:
        logger.info('Question generation fell back to stub: %s', exc)
    return _build_canned_mcq(topic_title, subject_name, count)


def _normalize_options(options) -> list[dict]:
    """QuestionGenerator returns options like 'A) answer'; normalize to
    [{'key': 'A', 'text': 'answer'}, ...] shape used by the student Chamber."""
    normalized = []
    for i, opt in enumerate(options or []):
        if isinstance(opt, dict):
            normalized.append({
                'key': opt.get('key', chr(65 + i)),
                'text': opt.get('text', ''),
            })
            continue
        s = str(opt).strip()
        # Try to split "A) answer" into key + text
        if len(s) >= 2 and s[0].isalpha() and s[1] in (')', '.', ':'):
            key = s[0].upper()
            text = s[2:].strip()
        else:
            key = chr(65 + i)
            text = s
        normalized.append({'key': key, 'text': text})
    return normalized


def _find_correct_key(correct_raw: str, options: list[dict]) -> str:
    """Translate the generator's `correct_answer` (e.g. 'A) answer' or 'answer')
    into the key character the student's Chamber expects."""
    if not correct_raw:
        return options[0]['key'] if options else ''
    c = str(correct_raw).strip()
    # If it's already a single letter
    if len(c) == 1 and c.isalpha():
        return c.upper()
    # "A) answer" style
    if len(c) >= 2 and c[0].isalpha() and c[1] in (')', '.', ':'):
        return c[0].upper()
    # Otherwise match on text
    for o in options:
        if o['text'].strip().lower() == c.lower():
            return o['key']
    # Last resort
    return options[0]['key'] if options else ''


@login_required
@role_required(['teacher', 'school_admin'])
def quest_create_view(request):
    classes = list(_teacher_classes(request.user))
    subjects = list(
        Subject.objects.filter(tenant=request.user.tenant, is_active=True)
        .order_by('name')
    )
    default_due = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()[:200]
        description = request.POST.get('description', '').strip()[:2000]
        class_id = request.POST.get('class_obj', '').strip()
        subject_id = request.POST.get('subject', '').strip()
        topic_id = request.POST.get('topic', '').strip()  # optional, ContentNode.pk
        count = int(request.POST.get('count', '5') or 5)
        difficulty = int(request.POST.get('difficulty', '3') or 3)
        due_date_raw = request.POST.get('due_date', '').strip()

        errors = []
        if not title:
            errors.append('Give the quest a title.')
        try:
            cls = Class.objects.get(pk=int(class_id), tenant=request.user.tenant)
        except (Class.DoesNotExist, ValueError):
            errors.append('Pick a class.')
            cls = None
        try:
            subject = Subject.objects.get(
                pk=int(subject_id), tenant=request.user.tenant,
            )
        except (Subject.DoesNotExist, ValueError):
            errors.append('Pick a subject.')
            subject = None

        try:
            due_date = timezone.datetime.strptime(
                due_date_raw, '%Y-%m-%dT%H:%M'
            ) if due_date_raw else None
            if due_date:
                due_date = timezone.make_aware(
                    due_date, timezone.get_current_timezone()
                )
        except ValueError:
            errors.append('Due date is invalid.')
            due_date = None
        if not due_date:
            errors.append('Pick a due date.')

        count = max(1, min(count, 20))
        difficulty = max(1, min(difficulty, 5))

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'teacher/quests/create.html', {
                'user': request.user,
                'classes': classes,
                'subjects': subjects,
                'default_due': default_due,
                'prior': {
                    'title': title, 'description': description,
                    'class_id': class_id, 'subject_id': subject_id,
                    'topic_id': topic_id, 'count': count,
                    'difficulty': difficulty, 'due_date': due_date_raw,
                },
                'active_page': 'quests',
            })

        # Resolve topic title for prompt
        topic_title = title
        if topic_id:
            try:
                node = ContentNode.objects.get(
                    pk=int(topic_id), tenant=request.user.tenant,
                )
                topic_title = node.title
            except (ContentNode.DoesNotExist, ValueError):
                pass

        difficulty_label = {1: 'easy', 2: 'easy', 3: 'medium', 4: 'hard', 5: 'hard'}[difficulty]

        generated = _generate_questions(topic_title, subject.name, count, difficulty_label)

        assignment = Assignment.objects.create(
            tenant=request.user.tenant,
            class_obj=cls,
            subject=subject,
            title=title,
            description=description,
            due_date=due_date,
            total_marks=len(generated),
            difficulty=difficulty,
            reward_xp=0,  # auto-derives on save()
            status=Assignment.STATUS_DRAFT,
            created_by=request.user,
            updated_by=request.user,
        )

        for i, q in enumerate(generated):
            options = _normalize_options(q.get('options'))
            correct_key = _find_correct_key(q.get('correct_answer'), options)
            Question.objects.create(
                assignment=assignment,
                order=i,
                question_type='mcq',
                question_text=q.get('question', f'Question {i + 1}'),
                options=options,
                correct_answer=correct_key,
                explanation=q.get('explanation', ''),
                marks=1,
            )

        messages.success(
            request,
            f'Draft quest "{assignment.title}" created with '
            f'{assignment.questions.count()} questions. Review and publish.',
        )
        return redirect('teacher:quest_detail', pk=assignment.id)

    return render(request, 'teacher/quests/create.html', {
        'user': request.user,
        'classes': classes,
        'subjects': subjects,
        'default_due': default_due,
        'prior': {},
        'active_page': 'quests',
    })


def _fetch_teacher_assignment(user, pk):
    return get_object_or_404(
        _teacher_assignments(user).filter(pk=pk),
    )


@login_required
@role_required(['teacher', 'school_admin'])
def quest_detail_view(request, pk):
    assignment = _fetch_teacher_assignment(request.user, pk)
    return render(request, 'teacher/quests/detail.html', {
        'user': request.user,
        'assignment': assignment,
        'questions': list(assignment.questions.all().order_by('order', 'id')),
        'active_page': 'quests',
    })


@login_required
@role_required(['teacher', 'school_admin'])
@require_POST
def quest_publish_view(request, pk):
    assignment = _fetch_teacher_assignment(request.user, pk)
    if assignment.status != Assignment.STATUS_DRAFT:
        messages.info(request, 'This quest is already published.')
        return redirect('teacher:quest_detail', pk=pk)
    if assignment.questions.count() == 0:
        messages.error(request, 'Add at least one question before publishing.')
        return redirect('teacher:quest_detail', pk=pk)
    assignment.publish()
    messages.success(request, f'Quest "{assignment.title}" published.')
    return redirect('teacher:quest_list')


@login_required
@role_required(['teacher', 'school_admin'])
@require_POST
def quest_archive_view(request, pk):
    assignment = _fetch_teacher_assignment(request.user, pk)
    assignment.status = Assignment.STATUS_ARCHIVED
    assignment.save(update_fields=['status', 'updated_at'])
    messages.info(request, f'Quest "{assignment.title}" archived.')
    return redirect('teacher:quest_list')
