from django.db import models
from apps.core.models.base import TenantAwareModel, TimestampedModel


class ContentNode(TenantAwareModel, TimestampedModel):
    NODE_TYPES = [
        ("chapter", "Chapter"),
        ("section", "Section"),
        ("topic", "Topic"),
        ("definition", "Definition"),
        ("formula", "Formula"),
        ("example", "Example"),
        ("exercise", "Exercise"),
        ("summary", "Summary"),
        ("key_point", "Key Point"),
    ]

    DIFFICULTY_LEVELS = [
        ("basic", "Basic"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    document = models.ForeignKey(
        "service.Document",
        on_delete=models.CASCADE,
        related_name="content_nodes",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    subject = models.ForeignKey(
        "service.Subject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    node_id = models.CharField(max_length=50)
    node_type = models.CharField(max_length=20, choices=NODE_TYPES)
    title = models.CharField(max_length=500)
    content = models.TextField(blank=True)
    content_plain = models.TextField(blank=True)
    page_number = models.IntegerField(null=True, blank=True)
    difficulty = models.CharField(
        max_length=20, choices=DIFFICULTY_LEVELS, null=True, blank=True
    )
    position = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict)
    embedding_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        ordering = ["document", "page_number", "position"]
        indexes = [
            models.Index(fields=["document", "node_type"]),
            models.Index(fields=["document", "parent"]),
            models.Index(fields=["subject"]),
        ]

    def __str__(self):
        return f"{self.node_id}: {self.title}"

    def get_descendants(self):
        """Get all descendants of this node (children, grandchildren, etc.)."""
        descendants = []
        children = list(self.children.all())
        descendants.extend(children)
        for child in children:
            descendants.extend(child.get_descendants())
        return descendants

    def depth(self):
        """Return depth in tree (0 = root)."""
        depth = 0
        node = self
        while node.parent is not None:
            depth += 1
            node = node.parent
        return depth
