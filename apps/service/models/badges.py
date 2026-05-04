"""Phase C — Badges (achievements).

Two tables:

- `Badge` — the catalog. One row per badge definition (code + name + icon +
  criteria rule). Static-ish; seeded via the `seed_badges` management
  command. `criteria` is a JSON rule spec that the badge engine
  (`apps.service.services.badges`) understands.

- `EarnedBadge` — the join. One row per (student, badge) once awarded.
  Unique constraint prevents re-awarding.

The engine calls `evaluate_and_award(student, event_type)` after every
relevant event (quest graded, hunt cleared, streak milestone, awakening
complete, rank-up). Hooks are wrapped in try/except so a badge failure
never breaks the primary event.
"""

from django.conf import settings
from django.db import models

from apps.core.models.base import TimestampedModel


class Badge(TimestampedModel):
    CATEGORY_AWAKENING = 'awakening'
    CATEGORY_QUEST = 'quest'
    CATEGORY_HUNT = 'hunt'
    CATEGORY_STREAK = 'streak'
    CATEGORY_RANK = 'rank'
    CATEGORY_CHOICES = [
        (CATEGORY_AWAKENING, 'Awakening'),
        (CATEGORY_QUEST, 'Quest'),
        (CATEGORY_HUNT, 'Hunt'),
        (CATEGORY_STREAK, 'Streak'),
        (CATEGORY_RANK, 'Rank'),
    ]

    RARITY_COMMON = 'common'
    RARITY_RARE = 'rare'
    RARITY_EPIC = 'epic'
    RARITY_LEGENDARY = 'legendary'
    RARITY_CHOICES = [
        (RARITY_COMMON, 'Common'),
        (RARITY_RARE, 'Rare'),
        (RARITY_EPIC, 'Epic'),
        (RARITY_LEGENDARY, 'Legendary'),
    ]

    # Stable slug used by the engine to resolve badges regardless of name changes.
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')

    # Visual treatment. `icon` is an emoji or single unicode char; the
    # profile template renders it inside a sys-chip with the matching
    # sys-* color variant per rarity.
    icon = models.CharField(max_length=20, default='★')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    rarity = models.CharField(max_length=20, choices=RARITY_CHOICES, default=RARITY_COMMON)

    # Rule spec consumed by `apps.service.services.badges.engine`. Shape:
    #   {'type': '<rule>', ...rule-specific params}
    # Supported rules: awakening_complete, quest_count (n),
    # quest_perfect, hunt_count (n), streak_days (n), rank_reached (rank).
    criteria = models.JSONField(default=dict, blank=True)

    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['category', 'display_order']),
            models.Index(fields=['is_active', 'display_order']),
        ]

    def __str__(self):
        return f'{self.icon} {self.name}'


class EarnedBadge(TimestampedModel):
    """Records that a student has earned a badge — one-shot per pair."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='earned_badges',
    )
    badge = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE,
        related_name='earned_by',
    )

    # Optional: link to the object that triggered the award (e.g. the
    # StudentAssignment pk for Perfectionist, the Goal pk for Hunter).
    related_object_type = models.CharField(max_length=50, blank=True, default='')
    related_object_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = [('student', 'badge')]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', '-created_at']),
        ]

    def __str__(self):
        return f'EarnedBadge<{self.student_id} {self.badge.code}>'
