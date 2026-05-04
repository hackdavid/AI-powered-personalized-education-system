"""Phase B — Goals (called "Hunts") + their Tasks (dungeon nodes)."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import TimestampedModel


class Goal(TimestampedModel):
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_EXPIRED = 'expired'
    STATUS_ABANDONED = 'abandoned'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_ABANDONED, 'Abandoned'),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='goals',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    subject = models.ForeignKey(
        'service.Subject', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='goals',
    )
    target_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    progress_pct = models.PositiveSmallIntegerField(default=0)
    xp_reward = models.PositiveIntegerField(default=200)

    decomposed_at = models.DateTimeField(null=True, blank=True)
    decomposition_error = models.TextField(blank=True, default='')
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['student', 'target_date']),
        ]

    def __str__(self):
        return f'Hunt<{self.student_id}: {self.title[:30]}>'

    def recompute_progress(self):
        total = self.tasks.count()
        done = self.tasks.filter(is_completed=True).count()
        self.progress_pct = int(round(100 * done / total)) if total else 0
        if total and done == total and self.status == self.STATUS_ACTIVE:
            self.status = self.STATUS_COMPLETED
            self.completed_at = timezone.now()
        self.save(update_fields=['progress_pct', 'status', 'completed_at', 'updated_at'])

    @property
    def days_remaining(self) -> int:
        delta = self.target_date - timezone.localdate()
        return max(0, delta.days)

    @property
    def is_overdue(self) -> bool:
        return self.status == self.STATUS_ACTIVE and self.target_date < timezone.localdate()

    def close_as_expired(self) -> int:
        """Mark an active Goal as expired. Returns the partial-XP amount the
        caller should award (0 if already closed or no progress)."""
        if self.completed_at is not None:
            return 0
        self.status = self.STATUS_EXPIRED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
        if self.progress_pct <= 0:
            return 0
        return int(round(self.xp_reward * self.progress_pct / 100))


class Task(TimestampedModel):
    KIND_READ = 'read'
    KIND_PRACTICE = 'practice'
    KIND_CHAT = 'chat'
    KIND_QUIZ = 'quiz'
    KIND_REFLECT = 'reflect'
    KIND_BOSS = 'boss'
    KIND_CHOICES = [
        (KIND_READ, 'Read'),
        (KIND_PRACTICE, 'Practice'),
        (KIND_CHAT, 'Chat'),
        (KIND_QUIZ, 'Quiz'),
        (KIND_REFLECT, 'Reflect'),
        (KIND_BOSS, 'Boss'),
    ]

    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name='tasks')
    order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_PRACTICE)
    xp_reward = models.PositiveIntegerField(default=25)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    ref_node = models.ForeignKey(
        'service.ContentNode', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='hunt_tasks',
    )

    # Per-task MCQ quiz — populated lazily on first "Begin" click by
    # `apps.service.services.hunts.quiz.ensure_quiz_questions`. Cached so
    # retries (after a fail) show the same questions and the student can
    # actually learn from the per-question feedback.
    quiz_questions = models.JSONField(default=list, blank=True)
    best_score_pct = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['goal', 'order', 'id']
        indexes = [models.Index(fields=['goal', 'is_completed'])]

    def __str__(self):
        return f'Task<{self.goal_id}: {self.title[:30]}>'

    def mark_completed(self):
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['is_completed', 'completed_at', 'updated_at'])
        self.goal.recompute_progress()

    def required_questions(self) -> int:
        """How many MCQs the student must answer to clear this task."""
        if self.kind == self.KIND_BOSS:
            return 10
        if self.kind in (self.KIND_QUIZ, self.KIND_PRACTICE):
            return 5
        return 3

    def pass_threshold_pct(self) -> int:
        """Percent correct required to clear the task (awards XP)."""
        return 70 if self.kind == self.KIND_BOSS else 67

    @property
    def action_label(self) -> str:
        """Button label on the dungeon map."""
        if self.is_completed:
            return 'Cleared'
        if self.kind == self.KIND_BOSS:
            return f'Engage Boss ({self.required_questions()}Q)'
        return f'Begin ({self.required_questions()}Q)'
