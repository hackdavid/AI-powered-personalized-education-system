"""Admin registrations for `apps.core`."""

from django.contrib import admin

from apps.core.models import AppSetting


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    """Admin for runtime-overridable settings.

    Secret values are masked in the changelist (only the last 4 chars are
    shown). Editing or viewing a single row reveals the value in plain
    text — admin access is already staff-only, so this is the right
    trade-off between auditability and copy-pasteability.
    """

    list_display = (
        'key',
        'category',
        'masked_value_display',
        'is_secret',
        'is_active',
        'updated_at',
        'updated_by',
    )
    list_filter = ('category', 'is_active', 'is_secret')
    search_fields = ('key', 'description')
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    fieldsets = (
        (None, {
            'fields': ('key', 'category', 'description'),
        }),
        ('Value', {
            'fields': ('value', 'is_secret', 'is_active'),
            'description': (
                'Changes do not take effect until the server restarts. '
                'After saving here, restart `runserver` (or your production '
                'process) to apply.'
            ),
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by', 'updated_at', 'updated_by'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Value', ordering='value')
    def masked_value_display(self, obj: AppSetting) -> str:
        return obj.masked_value or '—'

    def save_model(self, request, obj, form, change):
        """Stamp `created_by` / `updated_by` from the current admin user."""
        if not obj.pk and not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
