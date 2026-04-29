"""
Admin configuration for Accounts app.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Role, Permission


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model."""

    list_display = [
        'email',
        'first_name',
        'last_name',
        'role',
        'tenant',
        'is_active',
        'is_verified',
        'created_at'
    ]

    list_filter = [
        'is_active',
        'is_verified',
        'role',
        'tenant',
        'created_at'
    ]

    search_fields = [
        'email',
        'first_name',
        'last_name',
        'student_id',
        'employee_id'
    ]

    ordering = ['-created_at']

    readonly_fields = [
        'created_at',
        'updated_at',
        'last_login',
        'last_login_ip'
    ]

    fieldsets = (
        ('Authentication', {
            'fields': ('email', 'password')
        }),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'phone', 'avatar', 'bio')
        }),
        ('Access Control', {
            'fields': ('tenant', 'role', 'is_active', 'is_verified', 'is_staff', 'is_superuser'),
            'description': '''
                <div style="background: #FEF3C7; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;">
                    <strong>⚠️ Important:</strong>
                    <ul style="margin-top: 0.5rem; padding-left: 1.5rem;">
                        <li><strong>Django Superuser (is_superuser=True):</strong> Full technical access including Django Admin. Reserved for developers/tech admins.</li>
                        <li><strong>System Admin Role (role=System Admin):</strong> Business-level admin without Django Admin access. Cannot access this panel.</li>
                        <li><strong>Staff Status (is_staff):</strong> Only check this if you want the user to access Django Admin.</li>
                    </ul>
                    <p style="margin-top: 0.5rem;"><strong>To create a System Admin:</strong> Set role to "System Administrator" and leave is_superuser and is_staff unchecked.</p>
                </div>
            '''
        }),
        ('Student Information', {
            'fields': ('grade_level', 'student_id'),
            'classes': ('collapse',)
        }),
        ('Teacher Information', {
            'fields': ('employee_id', 'specialization'),
            'classes': ('collapse',)
        }),
        ('Preferences', {
            'fields': ('preferences',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'last_login', 'last_login_ip'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        ('Create New User', {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2', 'tenant', 'role')
        }),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin for Role model."""

    list_display = [
        'display_name',
        'name',
        'level',
        'is_active',
        'permission_count'
    ]

    list_filter = [
        'is_active',
        'level'
    ]

    search_fields = [
        'name',
        'display_name',
        'description'
    ]

    filter_horizontal = ['permissions']

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'display_name', 'description', 'level', 'is_active')
        }),
        ('Permissions', {
            'fields': ('permissions',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def permission_count(self, obj):
        """Display count of permissions."""
        return obj.permissions.count()

    permission_count.short_description = 'Permissions'


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """Admin for Permission model."""

    list_display = [
        'name',
        'code',
        'category',
        'role_count'
    ]

    list_filter = [
        'category',
        'created_at'
    ]

    search_fields = [
        'name',
        'code',
        'description'
    ]

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'category', 'description')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def role_count(self, obj):
        """Display count of roles with this permission."""
        return obj.roles.count()

    role_count.short_description = 'Roles'


# Tenant admin (formerly apps/tenants/admin.py)
from apps.accounts.models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'subscription_tier', 'created_at')
    list_filter = ('is_active', 'subscription_tier')
    search_fields = ('name', 'slug', 'domain')
    prepopulated_fields = {'slug': ('name',)}
