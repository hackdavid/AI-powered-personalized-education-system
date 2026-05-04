"""XPLedger service — records XP events, enforces daily cap, updates profile level/rank.

Every XP-earning action in the app calls `award_xp()`. Never manipulate
StudentProfile.total_xp / level / rank directly.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.service.models import StudentProfile, XPLedger

logger = logging.getLogger(__name__)


@dataclass
class XPAwardResult:
    awarded: int          # amount actually added (may be less than requested due to daily cap)
    requested: int        # amount caller asked for
    capped: bool          # True if daily cap clamped the award
    old_level: int
    new_level: int
    old_rank: str
    new_rank: str
    leveled_up: bool
    ranked_up: bool
    total_xp: int


def _reset_daily_counter_if_new_day(profile: StudentProfile) -> None:
    today = timezone.localdate()
    if profile.daily_xp_reset_date != today:
        profile.daily_xp_earned = 0
        profile.daily_xp_reset_date = today


@transaction.atomic
def award_xp(
    student,
    source: str,
    amount: int,
    description: str = '',
    related_object_type: str = '',
    related_object_id: Optional[int] = None,
    *,
    ignore_cap: bool = False,
) -> XPAwardResult:
    """Credit XP to a student. Creates a ledger row, updates profile, caps
    at DAILY_XP_CAP unless ignore_cap=True (used for admin adjustments)."""

    profile, _ = StudentProfile.objects.select_for_update().get_or_create(student=student)
    _reset_daily_counter_if_new_day(profile)

    old_level = profile.level
    old_rank = profile.rank
    requested = int(amount)

    # Clamp by daily cap (positive amounts only)
    if requested > 0 and not ignore_cap:
        remaining = max(0, StudentProfile.DAILY_XP_CAP - profile.daily_xp_earned)
        actual = min(requested, remaining)
    else:
        actual = requested

    capped = (actual != requested)

    if actual != 0:
        XPLedger.objects.create(
            student=student, source=source, amount=actual,
            description=description[:200],
            related_object_type=related_object_type[:50],
            related_object_id=related_object_id,
        )
        profile.total_xp = max(0, profile.total_xp + actual)
        if actual > 0:
            profile.daily_xp_earned += actual

        # Recompute level: increment while current_xp >= xp_for_next_level
        while profile.total_xp >= profile.xp_for_next_level():
            profile.level += 1
        # Or decrement if total_xp fell below current level threshold (negative adjust)
        while profile.level > 1 and profile.total_xp < profile.xp_for_current_level():
            profile.level -= 1

        profile.recalculate_rank()
        profile.save()

    # Badges hook: level-up / rank-up / new streak thresholds / hunt cleared
    # can all meet badge criteria after an award. Wrapped so a badge rule
    # failure never breaks the primary XP event.
    try:
        from apps.service.services.badges import evaluate_and_award
        evaluate_and_award(student, event_type=source or 'xp_awarded')
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning('Badge evaluation failed after award_xp: %s', exc)

    return XPAwardResult(
        awarded=actual,
        requested=requested,
        capped=capped,
        old_level=old_level,
        new_level=profile.level,
        old_rank=old_rank,
        new_rank=profile.rank,
        leveled_up=profile.level > old_level,
        ranked_up=profile.rank != old_rank,
        total_xp=profile.total_xp,
    )


def get_recent_xp_events(student, limit: int = 10):
    return list(XPLedger.objects.filter(student=student).order_by('-created_at')[:limit])
