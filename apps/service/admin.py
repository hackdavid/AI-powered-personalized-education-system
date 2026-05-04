"""Admin registrations for the service (domain) app."""

from django.contrib import admin

from apps.service.models import (
    Subject, Class, ClassSubject, Document,
    ContentNode, Asset, ContentCrossRef,
    TutoringSession, ChatMessage,
    ContentEmbedding,
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


@admin.register(TutoringSession)
class TutoringSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'student', 'subject', 'tenant', 'is_active', 'last_message_at')
    list_filter = ('is_active', 'tenant', 'subject')
    search_fields = ('title', 'student__email')
    readonly_fields = ('last_message_at',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'role', 'model', 'created_at')
    list_filter = ('role', 'model')
    search_fields = ('content',)
    readonly_fields = ('retrieved_chunks',)


@admin.register(ContentEmbedding)
class ContentEmbeddingAdmin(admin.ModelAdmin):
    """Read-only admin for embeddings — they're machine-generated."""
    list_display = ('id', 'content_node', 'model_name', 'tenant', 'created_at')
    list_filter = ('model_name', 'tenant')
    search_fields = ('content_node__node_id', 'content_node__title', 'embedding_id')
    readonly_fields = (
        'tenant', 'content_node', 'embedding_id', 'model_name',
        'embedding', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False  # created only by the seeding / ingestion pipelines

    def has_change_permission(self, request, obj=None):
        return False


# ===== Phase C — Badges =====

from apps.service.models.badges import Badge, EarnedBadge


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'icon', 'category', 'rarity', 'display_order', 'is_active')
    list_filter = ('category', 'rarity', 'is_active')
    search_fields = ('code', 'name', 'description')
    ordering = ('display_order', 'name')


@admin.register(EarnedBadge)
class EarnedBadgeAdmin(admin.ModelAdmin):
    list_display = ('student', 'badge', 'created_at')
    list_filter = ('badge__category', 'badge__rarity')
    search_fields = ('student__email', 'badge__code', 'badge__name')
    readonly_fields = ('created_at', 'updated_at')
