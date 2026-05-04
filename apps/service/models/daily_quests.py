"""Phase B — DailyQuest (system-generated, rule-based daily challenges)."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import TimestampedModel


class DailyQuest(TimestampedModel):
    KIND_VISIT_CHAT = 'visit_chat'
    KIND_PRACTICE_WEAKEST = 'practice_weakest'
    KIND_HUNT_TASK = 'hunt_task'
    KIND_STREAK = 'streak'
    KIND_CHOICES = [
        (KIND_VISIT_CHAT, 'Visit the System Advisor'),
        (KIND_PRACTICE_WEAKEST, 'Practice your weakest subject'),
        (KIND_HUNT_TASK, 'Complete a Hunt task'),
        (KIND_STREAK, 'Maintain your streak'),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_quests',
    )
    date = models.DateField(db_index=True)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    xp_reward = models.PositiveIntegerField(default=10)
    action_url = models.CharField(max_length=200, blank=True, default='')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('student', 'date', 'kind')]
        ordering = ['-date', 'kind']
        indexes = [models.Index(fields=['student', '-date'])]

    def __str__(self):
        return f'DQ<{self.student_id} {self.date} {self.kind}>'

    def mark_completed(self):
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['is_completed', 'completed_at', 'updated_at'])
