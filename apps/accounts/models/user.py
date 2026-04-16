"""
Custom User model with role-based access control and multi-tenant support.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from apps.core.models.base import TimestampedModel


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError('The Email field must be set')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser, TimestampedModel):
    """
    Custom User model with email authentication and role-based access.
    """

    # Remove username field, use email as primary identifier
    username = None

    email = models.EmailField(
        unique=True,
        verbose_name='Email Address',
        help_text='User email address (used for login)'
    )

    # Multi-tenant support
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
        verbose_name='School/Tenant',
        help_text='School this user belongs to (null for system admins)'
    )

    # Role-based access control
    role = models.ForeignKey(
        'accounts.Role',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
        verbose_name='User Role',
        help_text='Role determines permissions and dashboard access'
    )

    # Additional profile fields
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Phone Number'
    )

    avatar = models.ImageField(
        upload_to='avatars/',
        null=True,
        blank=True,
        verbose_name='Profile Picture'
    )

    bio = models.TextField(
        blank=True,
        null=True,
        verbose_name='Biography'
    )

    # Student-specific fields (only used if role=student)
    grade_level = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Grade Level',
        help_text='Current grade level for students'
    )

    student_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Student ID',
        help_text='School-assigned student ID'
    )

    # Teacher-specific fields (only used if role=teacher)
    employee_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Employee ID',
        help_text='School-assigned employee ID'
    )

    specialization = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Specialization',
        help_text='Subject specialization for teachers'
    )

    # Account status
    is_verified = models.BooleanField(
        default=False,
        verbose_name='Email Verified',
        help_text='Whether user has verified their email'
    )

    last_login_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='Last Login IP'
    )

    # Preferences
    preferences = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='User Preferences',
        help_text='User-specific settings and preferences'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'is_active']),
            models.Index(fields=['tenant', 'role']),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self):
        """Return the user's first name."""
        return self.first_name or self.email.split('@')[0]

    @property
    def role_name(self):
        """Get user's role name."""
        return self.role.name if self.role else None

    @property
    def is_student(self):
        """Check if user is a student."""
        return self.role_name == 'student'

    @property
    def is_teacher(self):
        """Check if user is a teacher."""
        return self.role_name == 'teacher'

    @property
    def is_school_admin(self):
        """Check if user is a school admin."""
        return self.role_name == 'school_admin'

    @property
    def is_system_admin(self):
        """
        Check if user is a system admin (role-based).
        Note: This is different from Django superuser (is_superuser).
        """
        return self.role_name == 'system_admin'

    @property
    def is_django_superuser(self):
        """Check if user is a Django superuser (technical admin)."""
        return self.is_superuser

    def has_permission(self, permission_code):
        """Check if user has a specific permission."""
        if not self.role:
            return False
        return self.role.has_permission(permission_code)

    def get_preference(self, key, default=None):
        """Get a user preference."""
        return self.preferences.get(key, default)

    def set_preference(self, key, value):
        """Set a user preference."""
        self.preferences[key] = value
        self.save(update_fields=['preferences'])
