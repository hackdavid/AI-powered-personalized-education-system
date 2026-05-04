"""Phase B — XPLedger: append-only audit of every XP event.

StudentProfile.total_xp is the cached sum; XPLedger is the source of truth
for analytics ("last 10 XP gains", weekly earnings, dispute resolution).
"""

from django.conf import settings
from django.db import models

from apps.core.models.base import TimestampedModel


class XPLedger(TimestampedModel):
    SOURCE_QUEST = 'quest'
    SOURCE_HUNT_TASK = 'hunt_task'
    SOURCE_HUNT_COMPLETE = 'hunt_complete'
    SOURCE_DAILY_QUEST = 'daily_quest'
    SOURCE_STREAK_MILESTONE = 'streak_milestone'
    SOURCE_AWAKENING = 'awakening'
    SOURCE_CHAT_ACTIVITY = 'chat_activity'
    SOURCE_ADMIN_ADJUSTMENT = 'admin_adjustment'
    SOURCE_CHOICES = [
        (SOURCE_QUEST, 'Quest'),
        (SOURCE_HUNT_TASK, 'Hunt Task'),
        (SOURCE_HUNT_COMPLETE, 'Hunt Complete'),
        (SOURCE_DAILY_QUEST, 'Daily Quest'),
        (SOURCE_STREAK_MILESTONE, 'Streak Milestone'),
        (SOURCE_AWAKENING, 'Awakening'),
        (SOURCE_CHAT_ACTIVITY, 'Chat Activity'),
        (SOURCE_ADMIN_ADJUSTMENT, 'Admin Adjustment'),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='xp_ledger',
    )
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    amount = models.IntegerField(help_text='Can be negative for corrections.')
    description = models.CharField(max_length=200, blank=True, default='')
    related_object_type = models.CharField(max_length=50, blank=True, default='')
    related_object_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['student', '-created_at'])]

    def __str__(self):
        return f'XP<{self.student_id} {self.amount:+d} {self.source}>'
