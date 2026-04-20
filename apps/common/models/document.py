"""
Document model for uploaded books and curriculum materials.
"""

import os
from django.db import models
from django.conf import settings
from apps.core.models.base import TenantAwareModel, AuditModel, TimestampedModel


def document_upload_path(instance, filename):
    return f"documents/{instance.tenant_id}/{instance.subject_id or 'general'}/{filename}"


class Document(TenantAwareModel, AuditModel):
    """Uploaded curriculum document / book for a subject and class."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_upload_path)
    file_type = models.CharField(max_length=10)
    file_size = models.PositiveBigIntegerField(default=0)
    subject = models.ForeignKey(
        'common.Subject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
    )
    class_obj = models.ForeignKey(
        'common.Class',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            self.file_size = self.file.size
        if self.file and not self.file_type:
            ext = os.path.splitext(self.file.name)[1].lstrip('.').lower()
            self.file_type = ext
        super().save(*args, **kwargs)
