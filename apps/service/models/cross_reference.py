from django.db import models
from apps.core.models.base import TenantAwareModel


class ContentCrossRef(TenantAwareModel):
    REF_TYPES = [
        ("prerequisite", "Prerequisite"),
        ("related", "Related"),
        ("extends", "Extends"),
        ("applies", "Applies"),
    ]

    source_node = models.ForeignKey(
        "service.ContentNode",
        on_delete=models.CASCADE,
        related_name="outgoing_refs",
    )
    target_node = models.ForeignKey(
        "service.ContentNode",
        on_delete=models.CASCADE,
        related_name="incoming_refs",
    )
    ref_type = models.CharField(max_length=20, choices=REF_TYPES)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = [["source_node", "target_node", "ref_type"]]

    def __str__(self):
        return f"{self.source_node.node_id} -> {self.target_node.node_id} ({self.ref_type})"
