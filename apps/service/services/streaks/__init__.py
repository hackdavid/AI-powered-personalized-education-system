"""Streak engine — computes daily activity streaks and fires milestone XP.

See `apps/service/services/streaks/engine.py` for the rules and entrypoint.
"""

from .engine import recompute_streak, STREAK_MILESTONES

__all__ = ['recompute_streak', 'STREAK_MILESTONES']
