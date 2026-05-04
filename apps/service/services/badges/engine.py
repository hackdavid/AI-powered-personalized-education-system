"""Badge rule evaluator.

`evaluate_and_award(student, event_type='')` loops over every active
`Badge`, evaluates `badge.criteria` against the student's current state,
and creates `EarnedBadge` rows for any newly-qualified badge.

Idempotent by design — `EarnedBadge` has a unique constraint on
`(student, badge)`. Safe to call from any event hook; failures are
swallowed by the hook wrapper so a broken badge rule never breaks the
originating event (grade / hunt / streak).

Criteria rule shapes supported:

    {'type': 'awakening_complete'}
    {'type': 'quest_count', 'n': <int>}
    {'type': 'quest_perfect'}
    {'type': 'hunt_count', 'n': <int>}
    {'type': 'streak_days', 'n': <int>}
    {'type': 'rank_reached', 'rank': 'D'|'C'|'B'|'A'|'S'}
"""

from __future__ import annotations

import logging
from typing import Dict, List

from django.db.models import F

from apps.service.models import (
    Badge, EarnedBadge, Goal, StudentAssignment, StudentProfile,
)

logger = logging.getLogger(__name__)

# Higher index = higher rank
_RANK_ORDER = ['E', 'D', 'C', 'B', 'A', 'S']


def _profile(student) -> StudentProfile | None:
    """Always fetch a fresh profile — the caller (e.g. `award_xp`) may have
    just updated `rank` / `level` / `streak_days` in the DB and we need to
    see those changes to award rank / streak badges."""
    return StudentProfile.objects.filter(student=student).first()


def _criterion_met(student, criteria: Dict) -> bool:
    """Evaluate one criterion dict against the student's current state."""
    if not isinstance(criteria, dict):
        return False
    rule = criteria.get('type')

    if rule == 'awakening_complete':
        p = _profile(student)
        return bool(p and p.onboarding_complete)

    if rule == 'quest_count':
        n = max(1, int(criteria.get('n', 1)))
        return StudentAssignment.objects.filter(
            student=student, status=StudentAssignment.STATUS_GRADED,
        ).count() >= n

    if rule == 'quest_perfect':
        # score == max_score, both > 0 (a quest with 0 max_score is trivially "perfect" — exclude it).
        return StudentAssignment.objects.filter(
            student=student,
            status=StudentAssignment.STATUS_GRADED,
            max_score__gt=0,
            score=F('max_score'),
        ).exists()

    if rule == 'hunt_count':
        n = max(1, int(criteria.get('n', 1)))
        return Goal.objects.filter(
            student=student, status=Goal.STATUS_COMPLETED,
        ).count() >= n

    if rule == 'streak_days':
        n = max(1, int(criteria.get('n', 1)))
        p = _profile(student)
        return bool(p and p.streak_days >= n)

    if rule == 'rank_reached':
        p = _profile(student)
        if not p:
            return False
        needed = str(criteria.get('rank', 'D')).upper()
        try:
            return _RANK_ORDER.index(p.rank) >= _RANK_ORDER.index(needed)
        except ValueError:
            return False

    logger.debug('Unknown badge criterion type: %r', rule)
    return False


def evaluate_and_award(student, event_type: str = '') -> List[EarnedBadge]:
    """Check every active badge against the student's state.
    Returns the list of newly-earned badges this call.
    """
    already = set(
        EarnedBadge.objects.filter(student=student).values_list('badge_id', flat=True)
    )
    candidates = Badge.objects.filter(is_active=True).exclude(pk__in=already)

    newly_earned: List[EarnedBadge] = []
    for badge in candidates:
        try:
            if _criterion_met(student, badge.criteria or {}):
                eb, created = EarnedBadge.objects.get_or_create(
                    student=student, badge=badge,
                    defaults={'related_object_type': event_type or ''},
                )
                if created:
                    newly_earned.append(eb)
                    logger.info(
                        'Badge awarded: student=%s badge=%s event=%s',
                        student.pk, badge.code, event_type,
                    )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                'Badge %s evaluation failed for student %s: %s',
                badge.code, student.pk, exc,
            )

    return newly_earned
