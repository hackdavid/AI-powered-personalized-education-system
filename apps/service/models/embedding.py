"""
ContentEmbedding — one vector per ContentNode per embedding model.

Lives in Supabase Postgres via the `pgvector` extension. Kept in a
separate table (rather than a column on ContentNode) so we can:

  * store multiple model versions per node (future A/B tests)
  * re-embed a tenant via `DELETE + INSERT` without a schema migration
  * index the vector column independently (HNSW, cosine ops)

Retrieval shape used by `CurriculumRetriever`:

    ContentEmbedding.objects
        .filter(tenant=tenant, model_name=settings.EMBEDDING_MODEL_NAME)
        .annotate(distance=CosineDistance('embedding', query_vector))
        .order_by('distance')
        .select_related('content_node__document')[:k]
"""

from django.db import models
from pgvector.django import VectorField

from apps.core.models.base import TenantAwareModel, TimestampedModel


# Dimension of the vectors we store. Matches the `all-MiniLM-L6-v2`
# model used by the remote embedder Space. When swapping models this
# value must match the new model's output dim — mismatch triggers a
# pgvector type error at insert time (good — fails loudly).
EMBEDDING_DIM = 384


class ContentEmbedding(TenantAwareModel, TimestampedModel):
    """A single embedding vector for one ContentNode under one model.

    The HNSW cosine-ops index lives in the migration (not here) so it
    can be gated on `connection.vendor == 'postgresql'`. SQLite test
    databases don't understand PostgreSQL's `WITH (...)` index syntax,
    so putting the index in Meta.indexes would break `manage.py test`.
    """

    content_node = models.ForeignKey(
        'service.ContentNode',
        on_delete=models.CASCADE,
        related_name='embeddings',
    )
    embedding = VectorField(dimensions=EMBEDDING_DIM)
    model_name = models.CharField(
        max_length=64,
        help_text='Embedding model identifier, e.g. all-MiniLM-L6-v2.',
    )
    # Legacy id format `<tenant_id>-<document_id>-<node_id>`, preserved
    # for logs / debugging. The unique_together below is the real key.
    embedding_id = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Content embedding'
        verbose_name_plural = 'Content embeddings'
        unique_together = [('content_node', 'model_name')]
        indexes = [
            models.Index(fields=['tenant', 'model_name']),
        ]

    def __str__(self) -> str:
        return f'Embedding({self.content_node_id}, {self.model_name})'
