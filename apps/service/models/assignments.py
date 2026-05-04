"""Phase B — Assignments (called "Quests" in the student UI).

Teachers create Assignments; students see them as quests on their
dashboard, take them via the Quest Chamber, and receive XP on submission.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import AuditModel, TenantAwareModel


class Assignment(TenantAwareModel, AuditModel):
    """A teacher-authored assignment targeted at a Class."""

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    instructions = models.TextField(blank=True, default='')

    class_obj = models.ForeignKey(
        'service.Class', on_delete=models.CASCADE, related_name='assignments',
    )
    subject = models.ForeignKey(
        'service.Subject', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assignments',
    )

    due_date = models.DateTimeField()
    total_marks = models.PositiveIntegerField(default=0)
    difficulty = models.PositiveSmallIntegerField(
        default=3,
        help_text='1 (easy) to 5 (hard); each star is ~20% XP multiplier.',
    )
    reward_xp = models.PositiveIntegerField(
        default=0,
        help_text='XP awarded on 100% score. Auto-derived if 0 at save time.',
    )
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=['tenant', 'class_obj', 'status']),
            models.Index(fields=['tenant', 'due_date']),
        ]

    def __str__(self):
        return f'{self.title} (due {self.due_date:%Y-%m-%d})'

    def save(self, *args, **kwargs):
        # Auto-derive reward_xp if unset: total_marks * difficulty * 5
        if not self.reward_xp and self.total_marks:
            self.reward_xp = self.total_marks * max(1, int(self.difficulty)) * 5
        super().save(*args, **kwargs)

    def publish(self):
        self.status = self.STATUS_PUBLISHED
        if not self.published_at:
            self.published_at = timezone.now()
        self.save(update_fields=['status', 'published_at', 'updated_at'])

    @property
    def is_overdue(self):
        return self.status == self.STATUS_PUBLISHED and self.due_date < timezone.now()


class Question(models.Model):
    """A single question inside an Assignment."""

    TYPE_MCQ = 'mcq'
    TYPE_SHORT = 'short'
    TYPE_ESSAY = 'essay'
    TYPE_UPLOAD = 'upload'
    TYPE_CHOICES = [
        (TYPE_MCQ, 'Multiple choice'),
        (TYPE_SHORT, 'Short answer'),
        (TYPE_ESSAY, 'Essay'),
        (TYPE_UPLOAD, 'File upload'),
    ]

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name='questions',
    )
    order = models.PositiveIntegerField(default=0)
    question_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MCQ)
    question_text = models.TextField()

    # For MCQ: list of {"key": "A", "text": "..."} (correct answer is stored separately
    # and NEVER sent to the student until grading completes).
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.CharField(max_length=500, blank=True, default='')
    explanation = models.TextField(blank=True, default='')
    marks = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['assignment', 'order', 'id']
        indexes = [models.Index(fields=['assignment', 'order'])]

    def __str__(self):
        return f'Q{self.order}: {self.question_text[:40]}'

    def is_auto_gradeable(self) -> bool:
        return self.question_type in (Question.TYPE_MCQ, Question.TYPE_SHORT)

    def student_visible_options(self):
        """Strip `is_correct` hints before sending to a student."""
        out = []
        for o in self.options:
            if isinstance(o, dict):
                out.append({k: v for k, v in o.items() if k != 'is_correct'})
            else:
                out.append({'key': str(o), 'text': str(o)})
        return out


class StudentAssignment(models.Model):
    """A student's attempt at an Assignment."""

    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_SUBMITTED = 'submitted'
    STATUS_GRADED = 'graded'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_GRADED, 'Graded'),
    ]

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name='student_assignments',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='student_assignments',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    score = models.PositiveIntegerField(null=True, blank=True)
    max_score = models.PositiveIntegerField(default=0)
    xp_awarded = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('assignment', 'student')]
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['assignment', 'status']),
        ]

    def __str__(self):
        return f'SA<{self.student_id} @ {self.assignment_id} {self.status}>'

    @property
    def score_percent(self) -> int:
        if not self.max_score:
            return 0
        return int(round(100 * (self.score or 0) / self.max_score))


class Answer(models.Model):
    """A single answer given by a student to a Question within a StudentAssignment."""

    student_assignment = models.ForeignKey(
        StudentAssignment, on_delete=models.CASCADE, related_name='answers',
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')

    selected_option_key = models.CharField(max_length=10, blank=True, default='')
    answer_text = models.TextField(blank=True, default='')
    file = models.FileField(upload_to='submissions/', null=True, blank=True)

    marks_awarded = models.PositiveIntegerField(null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    feedback = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('student_assignment', 'question')]
        indexes = [models.Index(fields=['student_assignment'])]

    def __str__(self):
        return f'A<Q{self.question_id} SA{self.student_assignment_id}>'
