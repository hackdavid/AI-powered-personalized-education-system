import os
import uuid

from django.db import models
from apps.core.models.base import TenantAwareModel, TimestampedModel


def asset_upload_path(instance, filename):
    tenant_id = instance.tenant_id or "unknown"
    ext = os.path.splitext(filename)[1]
    new_name = f"{uuid.uuid4().hex}{ext}"
    return os.path.join("assets", str(tenant_id), new_name)


class Asset(TenantAwareModel, TimestampedModel):
    ASSET_TYPES = [
        ("image", "Image"),
        ("table", "Table"),
        ("diagram", "Diagram"),
    ]

    document = models.ForeignKey(
        "service.Document",
        on_delete=models.CASCADE,
        related_name="assets",
    )
    content_node = models.ForeignKey(
        "service.ContentNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
    )
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPES)
    file = models.FileField(upload_to=asset_upload_path, blank=True)
    structured_data = models.JSONField(default=dict)
    description = models.TextField(blank=True)
    caption = models.TextField(blank=True)
    page_number = models.IntegerField(null=True, blank=True)
    asset_ref_id = models.CharField(max_length=100)

    class Meta:
        ordering = ["document", "page_number"]

    def __str__(self):
        return f"{self.asset_ref_id} ({self.asset_type})"
