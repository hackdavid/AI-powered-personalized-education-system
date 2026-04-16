"""
Admin configuration for Tenants app.
"""

from django.contrib import admin
from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """Admin interface for Tenant model."""

    list_display = [
        'name',
        'slug',
        'is_active',
        'subscription_tier',
        'max_students',
        'max_teachers',
        'created_at'
    ]

    list_filter = [
        'is_active',
        'subscription_tier',
        'created_at'
    ]

    search_fields = [
        'name',
        'slug',
        'email'
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'full_domain',
        'is_subscription_active'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('address', 'phone', 'email')
        }),
        ('Branding', {
            'fields': ('logo', 'primary_color')
        }),
        ('Domain Configuration', {
            'fields': ('domain', 'full_domain')
        }),
        ('Subscription', {
            'fields': ('subscription_tier', 'subscription_expires', 'is_subscription_active', 'max_students', 'max_teachers')
        }),
        ('Settings', {
            'fields': ('settings',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Override queryset to optimize queries."""
        qs = super().get_queryset(request)
        return qs.select_related()
