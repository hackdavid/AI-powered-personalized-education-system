"""Badges service.

- `evaluate_and_award(student, event_type)` — called after every eligible
  event (quest graded, hunt cleared, streak milestone, awakening
  complete, rank-up). Evaluates every active Badge's criteria against
  the student's current state and creates an `EarnedBadge` row for each
  newly-qualified one. Idempotent: already-earned badges are skipped.

- `STARTER_BADGES` — the seed catalog installed by the
  `seed_badges` management command.
"""

from .engine import evaluate_and_award
from .catalog import STARTER_BADGES

__all__ = ['evaluate_and_award', 'STARTER_BADGES']
