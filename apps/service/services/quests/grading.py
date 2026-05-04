"""Quest (Assignment) grading + attempt lifecycle.

Auto-grades MCQ + short-answer (exact match). Essay/upload questions are
marked `needs_review` — the graded status is only set when every question
is either auto-graded or has a teacher-set `marks_awarded`.
"""

import logging
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from apps.service.models import (
    Answer, Assignment, Question, StudentAssignment, XPLedger,
)
from apps.service.services.xp import award_xp

logger = logging.getLogger(__name__)


def start_attempt(student, assignment: Assignment) -> StudentAssignment:
    """Get or create the student's attempt; move to in_progress if pending."""
    sa, _ = StudentAssignment.objects.get_or_create(
        student=student, assignment=assignment,
        defaults={
            'max_score': assignment.total_marks,
            'status': StudentAssignment.STATUS_PENDING,
        },
    )
    if sa.status == StudentAssignment.STATUS_PENDING:
        sa.status = StudentAssignment.STATUS_IN_PROGRESS
        sa.started_at = timezone.now()
        if not sa.max_score:
            sa.max_score = assignment.total_marks
        sa.save(update_fields=['status', 'started_at', 'max_score', 'updated_at'])
    return sa


@transaction.atomic
def save_draft_answers(sa: StudentAssignment, answers: Iterable[dict]) -> int:
    """Upsert answer drafts. Input: iterable of {question_id, selected_option_key?, answer_text?}.
    Returns count of answers written."""
    if sa.status in (StudentAssignment.STATUS_SUBMITTED, StudentAssignment.STATUS_GRADED):
        return 0
    count = 0
    for data in answers:
        qid = data.get('question_id')
        if not qid:
            continue
        Answer.objects.update_or_create(
            student_assignment=sa, question_id=qid,
            defaults={
                'selected_option_key': (data.get('selected_option_key') or '')[:10],
                'answer_text': (data.get('answer_text') or '')[:20_000],
            },
        )
        count += 1
    # Bump status to in_progress if still pending
    if sa.status == StudentAssignment.STATUS_PENDING:
        sa.status = StudentAssignment.STATUS_IN_PROGRESS
        sa.started_at = sa.started_at or timezone.now()
        sa.save(update_fields=['status', 'started_at', 'updated_at'])
    return count


def _grade_one(answer: Answer) -> bool:
    """Apply auto-grading rules to a single Answer. Returns True if scored."""
    q = answer.question
    if q.question_type == Question.TYPE_MCQ:
        correct_key = (q.correct_answer or '').strip()
        selected = (answer.selected_option_key or '').strip()
        answer.is_correct = bool(correct_key) and selected == correct_key
        answer.marks_awarded = q.marks if answer.is_correct else 0
        answer.save(update_fields=['is_correct', 'marks_awarded', 'updated_at'])
        return True

    if q.question_type == Question.TYPE_SHORT:
        expected = (q.correct_answer or '').strip().lower()
        given = (answer.answer_text or '').strip().lower()
        answer.is_correct = bool(expected) and given == expected
        answer.marks_awarded = q.marks if answer.is_correct else 0
        answer.save(update_fields=['is_correct', 'marks_awarded', 'updated_at'])
        return True

    # Essay / upload: leave for teacher review.
    return False


@transaction.atomic
def grade_student_assignment(sa: StudentAssignment) -> StudentAssignment:
    """Submit + auto-grade the attempt. Awards XP for any portion auto-gradable.
    Essay/upload questions stay ungraded until a teacher sets `marks_awarded`."""
    if sa.status == StudentAssignment.STATUS_GRADED:
        return sa

    # Finalize submission state
    if not sa.submitted_at:
        sa.submitted_at = timezone.now()
    sa.status = StudentAssignment.STATUS_SUBMITTED
    sa.save(update_fields=['status', 'submitted_at', 'updated_at'])

    # Ensure every question has an Answer row (even empty) so we can tally
    existing = set(sa.answers.values_list('question_id', flat=True))
    for q in sa.assignment.questions.all():
        if q.id not in existing:
            Answer.objects.create(student_assignment=sa, question=q)

    # Auto-grade what we can
    fully_autogradable = True
    for answer in sa.answers.select_related('question').all():
        scored = _grade_one(answer)
        if not scored and answer.marks_awarded is None:
            fully_autogradable = False

    # Tally
    total = sum(a.marks_awarded or 0 for a in sa.answers.all())
    max_marks = sum(q.marks for q in sa.assignment.questions.all())
    sa.score = total
    sa.max_score = max_marks

    if fully_autogradable:
        sa.status = StudentAssignment.STATUS_GRADED
        sa.graded_at = timezone.now()
        # Award XP proportional to score
        base = sa.assignment.reward_xp or 0
        awarded_xp = int(round(base * (total / max_marks))) if max_marks else 0
        if awarded_xp > 0:
            res = award_xp(
                sa.student,
                source=XPLedger.SOURCE_QUEST,
                amount=awarded_xp,
                description=f'Quest: {sa.assignment.title[:120]}',
                related_object_type='assignment',
                related_object_id=sa.assignment_id,
            )
            sa.xp_awarded = res.awarded

        # Nudge subject mastery toward the student's score on this quest.
        try:
            from apps.service.services.mastery import apply_mastery_update
            profile = getattr(sa.student, 'profile', None)
            if profile and sa.assignment.subject_id:
                apply_mastery_update(profile, sa.assignment.subject_id, sa.score_percent)
        except Exception as exc:  # pragma: no cover
            logger.warning('Mastery update failed post-grade: %s', exc)
    sa.save(update_fields=['score', 'max_score', 'status', 'graded_at', 'xp_awarded', 'updated_at'])

    # After grading (and only if actually graded), mark any matching
    # MissionItem for today completed.
    if sa.status == StudentAssignment.STATUS_GRADED:
        try:
            from apps.service.services.missions import mark_item_completed_for_event
            mark_item_completed_for_event(
                sa.student, 'assignment', sa.assignment_id,
            )
        except Exception as exc:  # never let an analytics hook break grading
            logger.warning(
                'mark_item_completed_for_event failed after grading SA %s: %s',
                sa.pk, exc,
            )

        # Badges: Quest Novice / Quest Master / Perfectionist all trigger
        # here. award_xp above already evaluates; this re-pass catches the
        # case where XP was 0 (e.g. zero-score submission still counts
        # toward `quest_count` for Quest Master).
        try:
            from apps.service.services.badges import evaluate_and_award
            evaluate_and_award(sa.student, event_type='quest_graded')
        except Exception:  # pragma: no cover — defensive
            pass

    return sa
