"""Mastery moving-average service.

Every graded quest + passed hunt quiz calls `apply_mastery_update` to
nudge the student's `profile.mastery_per_subject[subject_id]` toward
their latest score using a 0.7/0.3 weighted moving average:

    updated = round(0.7 * old + 0.3 * new_pct)

- Default prior (never-probed subject): 50 (neutral).
- Score clamped to 0..100.
- No-op if subject_id is None.
"""

import logging
from typing import Optional

from apps.service.models import StudentProfile

logger = logging.getLogger(__name__)


DEFAULT_PRIOR = 50
HISTORY_WEIGHT = 0.7
NEW_SAMPLE_WEIGHT = 0.3


def apply_mastery_update(
    profile: StudentProfile,
    subject_id: Optional[int],
    score_pct: int,
) -> Optional[int]:
    """Apply a weighted-MA mastery update. Returns the new score or None."""
    if profile is None or subject_id is None:
        return None
    clamped = max(0, min(100, int(score_pct)))
    key = str(subject_id)
    mastery = profile.mastery_per_subject or {}
    old = int(mastery.get(key, DEFAULT_PRIOR))
    updated = int(round(HISTORY_WEIGHT * old + NEW_SAMPLE_WEIGHT * clamped))
    mastery[key] = updated
    profile.mastery_per_subject = mastery
    profile.save(update_fields=['mastery_per_subject', 'updated_at'])
    return updated
