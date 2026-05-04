"""Streak engine — rule-based daily streak computation + milestone bonuses.

The engine is idempotent per calendar day: the first call on a given
`profile.last_active_date` does the work; subsequent same-day calls
short-circuit. Safe to call on every dashboard visit.

Shield rules (`docs/student-redesign.md` §Soft streak):
  * A student gets 1 shield per week.
  * Weekly refill happens on Monday (local time) to max 1.
  * A shield "eats" a single missed day without breaking the chain.

Milestones are awarded via `apps.service.services.xp.award_xp` and persisted
on the ledger as `XPLedger.SOURCE_STREAK_MILESTONE` rows. Each milestone
fires at most once per student (tracked in
`StudentProfile.preferences['streak_milestones_hit']`).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Dict, List

from django.db import transaction
from django.utils import timezone

from apps.service.models import StudentProfile, XPLedger
from apps.service.services.xp import award_xp

logger = logging.getLogger(__name__)


# Day → XP bonus. Hit thresholds once each, ever.
STREAK_MILESTONES = {7: 100, 30: 500, 100: 1000}

# How far back we walk when rebuilding the streak. 30 days matches the
# 30-day milestone; anything older wouldn't affect the current streak anyway.
LOOKBACK_CAP_DAYS = 30


# Only the streak-related columns get persisted here so a concurrent
# `award_xp` call (fired below for milestones) can't be clobbered.
_STREAK_UPDATE_FIELDS = [
    'streak_days',
    'streak_shields_remaining',
    'last_active_date',
    'last_shield_refill_date',
    'preferences',
    'updated_at',
]


@transaction.atomic
def recompute_streak(profile: StudentProfile) -> Dict:
    """Recompute `profile.streak_days` + `streak_shields_remaining` in place.

    Also fires any newly-earned STREAK_MILESTONES bonuses via `award_xp`.
    Idempotent per calendar day.

    Returns a small result dict:
        {
            'ran': bool,             # True if work was done, False if no-op
            'streak_days': int,      # current streak AFTER recompute
            'shields': int,          # shields AFTER recompute
            'milestones_fired': [int, ...],  # days that fired this call
        }
    """
    today = timezone.localdate()

    # Same-day idempotence. If we already computed today, return the cached
    # values verbatim — the engine is a no-op for this visit.
    if profile.last_active_date == today:
        return {
            'ran': False,
            'streak_days': profile.streak_days,
            'shields': profile.streak_shields_remaining,
            'milestones_fired': [],
        }

    # --- Weekly shield refill ---------------------------------------------
    this_monday = today - timedelta(days=today.weekday())
    if (
        profile.last_shield_refill_date is None
        or profile.last_shield_refill_date < this_monday
    ):
        # Cap at 1 — prevent hoarding across weeks.
        profile.streak_shields_remaining = max(profile.streak_shields_remaining, 1)
        profile.last_shield_refill_date = today

    # --- Walk backwards to compute streak ---------------------------------
    # Shields are "bridges" — they only spend themselves to keep an existing
    # streak alive across a missed day. A student with no activity at all
    # doesn't burn shields on leading empty days; otherwise the weekly
    # refill would be invisible by the time we save.
    shields_left = profile.streak_shields_remaining
    streak = 0
    for offset in range(LOOKBACK_CAP_DAYS + 1):
        d = today - timedelta(days=offset)
        has_xp = XPLedger.objects.filter(
            student=profile.student, created_at__date=d,
        ).exists()
        if offset == 0:
            # Today: an XP event extends the streak by 1. Empty "today"
            # doesn't reset — just doesn't add yet.
            if has_xp:
                streak += 1
            continue
        if has_xp:
            streak += 1
        else:
            # Missed day — burn a shield only if we have a streak going.
            if streak > 0 and shields_left > 0:
                shields_left -= 1
                continue
            break

    # --- Determine which milestones should fire ---------------------------
    prefs = profile.preferences if isinstance(profile.preferences, dict) else {}
    hit_set = set(prefs.get('streak_milestones_hit', []) or [])
    to_fire: List[tuple] = []
    for d, bonus in sorted(STREAK_MILESTONES.items()):
        if streak >= d and d not in hit_set:
            to_fire.append((d, bonus))
            hit_set.add(d)

    # --- Persist streak fields (ONLY the streak columns) ------------------
    # Using update_fields keeps us from clobbering total_xp / level / rank
    # which award_xp will mutate on its own StudentProfile fetch below.
    profile.streak_shields_remaining = shields_left
    profile.streak_days = streak
    profile.last_active_date = today
    prefs['streak_milestones_hit'] = sorted(hit_set)
    profile.preferences = prefs
    profile.save(update_fields=_STREAK_UPDATE_FIELDS)

    # --- Fire milestone XP bonuses AFTER the streak save ------------------
    fired: List[int] = []
    for d, bonus in to_fire:
        try:
            award_xp(
                profile.student,
                source=XPLedger.SOURCE_STREAK_MILESTONE,
                amount=int(bonus),
                description=f'{d}-day streak',
                ignore_cap=True,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                'streak milestone award failed (student=%s, d=%s): %s',
                profile.student_id, d, exc,
            )
            continue
        fired.append(d)

    # Refresh so the caller sees the post-award values (level / xp may have
    # moved).
    profile.refresh_from_db()

    return {
        'ran': True,
        'streak_days': profile.streak_days,
        'shields': profile.streak_shields_remaining,
        'milestones_fired': fired,
    }
