"""
Enrollment — explicit many-to-many link between Class and student User.
Replaces the implicit 'tenant + grade_level' matching with a real join table.
"""

from django.conf import settings
from django.db import models

from apps.core.models.base import TimestampedModel


class Enrollment(TimestampedModel):
    class_obj = models.ForeignKey(
        'service.Class',
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='class_enrollments',
    )
    enrolled_on = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('class_obj', 'student')]
        indexes = [
            models.Index(fields=['class_obj', 'is_active']),
            models.Index(fields=['student', 'is_active']),
        ]

    def __str__(self):
        return f'Enrollment<{self.student_id} in {self.class_obj_id}>'
