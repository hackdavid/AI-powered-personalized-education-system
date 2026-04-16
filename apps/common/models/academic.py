"""
Academic models - Subject, Class, and their relationships.
"""

from django.db import models
from django.conf import settings
from apps.core.models.base import TenantAwareModel, TimestampedModel


class Subject(TenantAwareModel, TimestampedModel):
    """
    Subject model representing academic subjects (e.g., Mathematics, English).
    """

    name = models.CharField(
        max_length=100,
        verbose_name='Subject Name',
        help_text='Name of the subject (e.g., Mathematics, English)'
    )

    code = models.CharField(
        max_length=20,
        verbose_name='Subject Code',
        help_text='Short code for the subject (e.g., MATH, ENG)'
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name='Description',
        help_text='Brief description of the subject'
    )

    color = models.CharField(
        max_length=7,
        default='#6366F1',
        verbose_name='Color',
        help_text='Color code for UI display (hex format)'
    )

    icon = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Icon',
        help_text='Icon name for UI display'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='Active',
        help_text='Whether this subject is currently active'
    )

    class Meta:
        verbose_name = 'Subject'
        verbose_name_plural = 'Subjects'
        ordering = ['name']
        unique_together = [['tenant', 'code']]
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Class(TenantAwareModel, TimestampedModel):
    """
    Class model representing a class/section (e.g., Grade 8 - Section A).
    """

    name = models.CharField(
        max_length=100,
        verbose_name='Class Name',
        help_text='Name of the class (e.g., Grade 8 - Section A)'
    )

    grade_level = models.IntegerField(
        verbose_name='Grade Level',
        help_text='Grade level (1-12)'
    )

    section = models.CharField(
        max_length=10,
        default='A',
        verbose_name='Section',
        help_text='Section identifier (A, B, C, etc.)'
    )

    academic_year = models.CharField(
        max_length=20,
        verbose_name='Academic Year',
        help_text='Academic year (e.g., 2024-2025)'
    )

    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_classes',
        verbose_name='Class Teacher',
        help_text='Primary teacher responsible for this class'
    )

    max_students = models.IntegerField(
        default=30,
        verbose_name='Maximum Students',
        help_text='Maximum number of students allowed in this class'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='Active',
        help_text='Whether this class is currently active'
    )

    class Meta:
        verbose_name = 'Class'
        verbose_name_plural = 'Classes'
        ordering = ['grade_level', 'section']
        unique_together = [['tenant', 'grade_level', 'section', 'academic_year']]
        indexes = [
            models.Index(fields=['tenant', 'academic_year', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.academic_year})"

    @property
    def student_count(self):
        """Get the number of students in this class."""
        return self.students.count()

    @property
    def is_full(self):
        """Check if class has reached maximum capacity."""
        return self.student_count >= self.max_students


class ClassSubject(TimestampedModel):
    """
    ClassSubject model representing the assignment of a subject to a class with a teacher.
    """

    class_obj = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='class_subjects',
        verbose_name='Class'
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='class_subjects',
        verbose_name='Subject'
    )

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='taught_subjects',
        verbose_name='Teacher',
        help_text='Teacher assigned to teach this subject for this class'
    )

    schedule = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Schedule',
        help_text='Weekly schedule for this subject (days, times)'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='Active'
    )

    class Meta:
        verbose_name = 'Class Subject'
        verbose_name_plural = 'Class Subjects'
        ordering = ['class_obj', 'subject']
        unique_together = [['class_obj', 'subject']]
        indexes = [
            models.Index(fields=['class_obj', 'is_active']),
            models.Index(fields=['teacher', 'is_active']),
        ]

    def __str__(self):
        return f"{self.class_obj.name} - {self.subject.name}"

    @property
    def tenant(self):
        """Get tenant from related class."""
        return self.class_obj.tenant
