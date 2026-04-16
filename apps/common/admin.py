"""
Admin configuration for Common app.
"""

from django.contrib import admin
from .models import Subject, Class, ClassSubject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """Admin for Subject model."""

    list_display = [
        'name',
        'code',
        'tenant',
        'color',
        'is_active',
        'created_at'
    ]

    list_filter = [
        'is_active',
        'tenant',
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
            'fields': ('tenant', 'name', 'code', 'description')
        }),
        ('Display', {
            'fields': ('color', 'icon')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    """Admin for Class model."""

    list_display = [
        'name',
        'grade_level',
        'section',
        'academic_year',
        'class_teacher',
        'student_count',
        'max_students',
        'is_active'
    ]

    list_filter = [
        'is_active',
        'tenant',
        'academic_year',
        'grade_level'
    ]

    search_fields = [
        'name',
        'grade_level',
        'section'
    ]

    readonly_fields = ['created_at', 'updated_at', 'student_count', 'is_full']

    fieldsets = (
        ('Basic Information', {
            'fields': ('tenant', 'name', 'grade_level', 'section', 'academic_year')
        }),
        ('Management', {
            'fields': ('class_teacher', 'max_students', 'student_count', 'is_full')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def student_count(self, obj):
        """Display student count."""
        return obj.student_count

    student_count.short_description = 'Students'


@admin.register(ClassSubject)
class ClassSubjectAdmin(admin.ModelAdmin):
    """Admin for ClassSubject model."""

    list_display = [
        'class_obj',
        'subject',
        'teacher',
        'is_active',
        'created_at'
    ]

    list_filter = [
        'is_active',
        'class_obj__academic_year',
        'created_at'
    ]

    search_fields = [
        'class_obj__name',
        'subject__name',
        'teacher__email'
    ]

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Assignment', {
            'fields': ('class_obj', 'subject', 'teacher')
        }),
        ('Schedule', {
            'fields': ('schedule',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
