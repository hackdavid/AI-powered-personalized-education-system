"""
StudentProfile — per-student gamification state (XP, level, rank, streak, mastery).
One-to-one with User. Authoritative source for all student-visible progression.
"""

from django.conf import settings
from django.db import models

from apps.core.models.base import TimestampedModel


class StudentProfile(TimestampedModel):
    """Persistent gamification state for a student."""

    RANK_E = 'E'
    RANK_D = 'D'
    RANK_C = 'C'
    RANK_B = 'B'
    RANK_A = 'A'
    RANK_S = 'S'
    RANK_CHOICES = [
        (RANK_E, 'E'), (RANK_D, 'D'), (RANK_C, 'C'),
        (RANK_B, 'B'), (RANK_A, 'A'), (RANK_S, 'S'),
    ]

    DAILY_XP_CAP = 1000

    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )

    hunter_title = models.CharField(max_length=50, blank=True, default='')
    total_xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)
    rank = models.CharField(max_length=1, choices=RANK_CHOICES, default=RANK_E)

    streak_days = models.PositiveIntegerField(default=0)
    streak_shields_remaining = models.PositiveSmallIntegerField(default=1)
    last_active_date = models.DateField(null=True, blank=True)
    last_shield_refill_date = models.DateField(null=True, blank=True)

    daily_xp_earned = models.PositiveIntegerField(default=0)
    daily_xp_reset_date = models.DateField(null=True, blank=True)

    mastery_per_subject = models.JSONField(default=dict, blank=True,
        help_text='{subject_id: 0-100}')
    learning_style = models.JSONField(default=dict, blank=True,
        help_text='VARK profile from onboarding')
    interest_tags = models.JSONField(default=list, blank=True)

    # Generic per-student engine state (streak milestones hit, future flags,
    # etc.) — migration 0009 adds this column. Prefer this bucket over adding
    # narrow single-use columns.
    preferences = models.JSONField(
        default=dict,
        blank=True,
        help_text='Misc student preferences / engine state (e.g. streak milestones hit).',
    )

    onboarding_complete = models.BooleanField(default=False, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'onboarding_complete']),
        ]

    def __str__(self):
        return f'Profile<{self.student_id}: Lv{self.level} {self.rank}>'

    def xp_for_level(self, n: int) -> int:
        """Total XP required to have reached level n. Level 1 = 0."""
        if n <= 1:
            return 0
        return int(100 * (n ** 1.5))

    def xp_for_next_level(self) -> int:
        return self.xp_for_level(self.level + 1)

    def xp_for_current_level(self) -> int:
        return self.xp_for_level(self.level)

    def xp_progress_pct(self) -> float:
        low = self.xp_for_current_level()
        high = self.xp_for_next_level()
        if high <= low:
            return 100.0
        return max(0.0, min(100.0, (self.total_xp - low) / (high - low) * 100.0))

    def recalculate_rank(self) -> str:
        L = self.level
        if L >= 80:
            new_rank = self.RANK_S
        elif L >= 55:
            new_rank = self.RANK_A
        elif L >= 35:
            new_rank = self.RANK_B
        elif L >= 20:
            new_rank = self.RANK_C
        elif L >= 10:
            new_rank = self.RANK_D
        else:
            new_rank = self.RANK_E
        self.rank = new_rank
        return new_rank
