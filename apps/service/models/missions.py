"""
MissionBrief + MissionItem — the durable, personalized daily mission slate.
See docs/student-redesign.md for the full lifecycle.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import TimestampedModel


class MissionBrief(TimestampedModel):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mission_briefs',
    )
    date = models.DateField(db_index=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    all_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('student', 'date')]
        indexes = [
            models.Index(fields=['student', '-date']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f'MissionBrief<{self.student_id} {self.date}>'

    def mark_all_completed_if_done(self):
        if not self.items.exclude(status__in=[
            MissionItem.STATUS_COMPLETED, MissionItem.STATUS_EXPIRED
        ]).exists():
            if not self.all_completed_at:
                self.all_completed_at = timezone.now()
                self.save(update_fields=['all_completed_at', 'updated_at'])


class MissionItem(TimestampedModel):
    KIND_QUEST = 'quest'
    KIND_HUNT_TASK = 'hunt_task'
    KIND_PRACTICE = 'practice'
    KIND_CHAT = 'chat'
    KIND_STREAK = 'streak'
    KIND_URGENT = 'urgent_quest'
    KIND_CHOICES = [
        (KIND_QUEST, 'Quest'),
        (KIND_HUNT_TASK, 'Hunt Task'),
        (KIND_PRACTICE, 'Practice'),
        (KIND_CHAT, 'Chat'),
        (KIND_STREAK, 'Streak'),
        (KIND_URGENT, 'Urgent Quest'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    brief = models.ForeignKey(
        MissionBrief,
        on_delete=models.CASCADE,
        related_name='items',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    xp_reward = models.PositiveIntegerField(default=0)
    priority = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING,
    )
    action_url = models.CharField(max_length=200, blank=True, default='')
    related_object_type = models.CharField(max_length=50, blank=True, default='')
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-priority', 'id']
        indexes = [
            models.Index(fields=['brief', 'status']),
            models.Index(fields=['brief', '-priority']),
        ]

    def __str__(self):
        return f'MissionItem<{self.title[:30]} status={self.status}>'

    def mark_completed(self):
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
        self.brief.mark_all_completed_if_done()
