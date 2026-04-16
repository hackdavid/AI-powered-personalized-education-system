"""
Tenant models for multi-tenant architecture.
Each tenant represents a school with isolated data.
"""

from django.db import models
from django.utils.text import slugify
from apps.core.models.base import TimestampedModel


class Tenant(TimestampedModel):
    """
    Tenant model representing a school or organization.
    All tenant-specific data should be linked to a Tenant instance.
    """

    name = models.CharField(
        max_length=255,
        verbose_name='School Name',
        help_text='Full name of the school or organization'
    )

    slug = models.SlugField(
        unique=True,
        max_length=100,
        verbose_name='Subdomain',
        help_text='Unique subdomain identifier (e.g., "springfield" for springfield.eduai.com)'
    )

    domain = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Custom Domain',
        help_text='Optional custom domain (e.g., "school.edu")'
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name='Active Status',
        help_text='Inactive tenants cannot be accessed'
    )

    # School Information
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # Branding
    logo = models.ImageField(
        upload_to='tenant_logos/',
        null=True,
        blank=True,
        help_text='School logo'
    )

    primary_color = models.CharField(
        max_length=7,
        default='#4F46E5',
        help_text='Primary brand color (hex format)'
    )

    # Tenant-specific settings (JSON field for flexibility)
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text='School-specific configuration and preferences'
    )

    # Subscription information (for future billing)
    subscription_tier = models.CharField(
        max_length=50,
        default='free',
        choices=[
            ('free', 'Free'),
            ('basic', 'Basic'),
            ('premium', 'Premium'),
            ('enterprise', 'Enterprise'),
        ]
    )

    subscription_expires = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Subscription expiration date'
    )

    max_students = models.IntegerField(
        default=100,
        help_text='Maximum number of students allowed'
    )

    max_teachers = models.IntegerField(
        default=10,
        help_text='Maximum number of teachers allowed'
    )

    class Meta:
        verbose_name = 'Tenant'
        verbose_name_plural = 'Tenants'
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug', 'is_active']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Auto-generate slug from name if not provided."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def full_domain(self):
        """Get the full domain for this tenant."""
        if self.domain:
            return self.domain
        return f"{self.slug}.eduai.local"  # Change to your domain

    @property
    def is_subscription_active(self):
        """Check if subscription is active."""
        if self.subscription_tier == 'free':
            return True
        if not self.subscription_expires:
            return False
        from django.utils import timezone
        return timezone.now() < self.subscription_expires

    def get_setting(self, key, default=None):
        """Get a tenant-specific setting."""
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        """Set a tenant-specific setting."""
        self.settings[key] = value
        self.save(update_fields=['settings'])
