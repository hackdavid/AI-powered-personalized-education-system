"""Admin registrations for the service (domain) app."""

from django.contrib import admin

from apps.service.models import (
    Subject, Class, ClassSubject, Document,
    ContentNode, Asset, ContentCrossRef,
)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'tenant', 'color', 'is_active', 'created_at')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'code')


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'grade_level', 'section', 'academic_year',
        'class_teacher', 'student_count', 'max_students', 'is_active',
    )
    list_filter = ('is_active', 'grade_level', 'academic_year', 'tenant')
    search_fields = ('name', 'section')


@admin.register(ClassSubject)
class ClassSubjectAdmin(admin.ModelAdmin):
    list_display = ('class_obj', 'subject', 'teacher', 'is_active', 'created_at')
    list_filter = ('is_active',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'source_type', 'file_type', 'file_size', 'subject', 'class_obj', 'status', 'created_at')
    list_filter = ('source_type', 'status', 'file_type', 'tenant')
    search_fields = ('title',)
    readonly_fields = ('file_size', 'file_type')


@admin.register(ContentNode)
class ContentNodeAdmin(admin.ModelAdmin):
    list_display = ('node_id', 'title', 'node_type', 'document', 'parent', 'page_number')
    list_filter = ('node_type', 'difficulty', 'tenant')
    search_fields = ('node_id', 'title')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('asset_ref_id', 'asset_type', 'content_node', 'page_number')
    list_filter = ('asset_type',)


@admin.register(ContentCrossRef)
class ContentCrossRefAdmin(admin.ModelAdmin):
    list_display = ('source_node', 'target_node', 'ref_type')
    list_filter = ('ref_type',)
