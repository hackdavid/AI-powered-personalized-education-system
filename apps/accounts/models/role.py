"""
Role and Permission models for RBAC.
"""

from django.db import models
from apps.core.models.base import TimestampedModel


class Permission(TimestampedModel):
    """
    Permission model representing specific actions users can perform.
    """

    code = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Permission Code',
        help_text='Unique identifier for the permission (e.g., "view_student_grades")'
    )

    name = models.CharField(
        max_length=255,
        verbose_name='Permission Name',
        help_text='Human-readable permission name'
    )

    description = models.TextField(
        blank=True,
        help_text='Detailed description of what this permission allows'
    )

    category = models.CharField(
        max_length=50,
        default='general',
        help_text='Permission category for grouping'
    )

    class Meta:
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Role(TimestampedModel):
    """
    Role model for role-based access control.
    Each user is assigned a role which determines their permissions.
    """

    # Role constants
    STUDENT = 'student'
    TEACHER = 'teacher'
    SCHOOL_ADMIN = 'school_admin'
    SYSTEM_ADMIN = 'system_admin'

    ROLE_CHOICES = [
        (STUDENT, 'Student'),
        (TEACHER, 'Teacher'),
        (SCHOOL_ADMIN, 'School Administrator'),
        (SYSTEM_ADMIN, 'System Administrator'),
    ]

    name = models.CharField(
        max_length=50,
        unique=True,
        choices=ROLE_CHOICES,
        verbose_name='Role Name'
    )

    display_name = models.CharField(
        max_length=100,
        verbose_name='Display Name',
        help_text='Friendly name shown in UI'
    )

    description = models.TextField(
        blank=True,
        help_text='Description of role responsibilities'
    )

    permissions = models.ManyToManyField(
        Permission,
        related_name='roles',
        blank=True,
        verbose_name='Permissions',
        help_text='Permissions granted to this role'
    )

    is_active = models.BooleanField(
        default=True,
        help_text='Whether this role can be assigned to users'
    )

    # Hierarchy level (lower number = higher privilege)
    level = models.IntegerField(
        default=100,
        help_text='Role hierarchy level (1=highest, 100=lowest)'
    )

    class Meta:
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['level', 'name']

    def __str__(self):
        return self.display_name

    def has_permission(self, permission_code):
        """Check if role has a specific permission."""
        return self.permissions.filter(code=permission_code).exists()

    def grant_permission(self, permission_code):
        """Grant a permission to this role."""
        try:
            permission = Permission.objects.get(code=permission_code)
            self.permissions.add(permission)
        except Permission.DoesNotExist:
            raise ValueError(f"Permission '{permission_code}' does not exist")

    def revoke_permission(self, permission_code):
        """Revoke a permission from this role."""
        try:
            permission = Permission.objects.get(code=permission_code)
            self.permissions.remove(permission)
        except Permission.DoesNotExist:
            pass
