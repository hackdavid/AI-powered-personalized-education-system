"""
Tutoring (RAG chat) models.

A `TutoringSession` is a student-owned conversation, scoped to a tenant and
optionally a subject. Each `ChatMessage` belongs to a session and carries the
prompt or grounded answer plus, for assistant messages, the retrieved source
chunks used to build the answer.
"""

from django.conf import settings
from django.db import models

from apps.core.models.base import TenantAwareModel, TimestampedModel


class TutoringSession(TenantAwareModel, TimestampedModel):
    """One ongoing chat conversation owned by a single student."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tutoring_sessions',
    )
    subject = models.ForeignKey(
        'service.Subject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tutoring_sessions',
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text='Auto-derived from the first user question; editable.',
    )
    is_active = models.BooleanField(default=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'student', '-last_message_at']),
        ]

    def __str__(self):
        return self.title or f'Session {self.pk}'


class ChatMessage(TimestampedModel):
    """A single user turn or assistant turn within a session."""

    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        ASSISTANT = 'assistant', 'Assistant'

    session = models.ForeignKey(
        TutoringSession,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    retrieved_chunks = models.JSONField(
        default=list,
        blank=True,
        help_text='List of {node_id, document_id, title, score, snippet, page_number} dicts. Empty for student turns.',
    )
    model = models.CharField(
        max_length=64,
        blank=True,
        help_text="LLM identifier (e.g. 'gpt-4', 'stub'). Empty for student turns.",
    )

    class Meta:
        ordering = ['session', 'created_at']
        indexes = [
            models.Index(fields=['session', 'created_at']),
        ]

    def __str__(self):
        return f'{self.role}: {self.content[:60]}'

    @property
    def tenant(self):
        """Convenience: derive tenant from the parent session for templates / RBAC."""
        return self.session.tenant
