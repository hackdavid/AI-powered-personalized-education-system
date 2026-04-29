"""
pgvector-backed vector store client.

Replaces the previous ChromaDB-on-disk implementation. Storage now lives
in the same Postgres (Supabase) as the rest of the ORM data, so there's
no extra persistent directory, no separate server, and embeddings are
shared across every team-mate's machine.

Public surface is intentionally the same as the old ChromaDB client so
`CurriculumRetriever`, `ContentStorage`, and `seed_synthetic_data` all
keep working without edits:

    vs = VectorStoreClient()
    col = vs.get_or_create_collection(str(tenant.id), 'curriculum')
    vs.add_documents(col, documents=[...], metadatas=[...], ids=[...])
    col.delete(ids=[...])              # idempotent-upsert pattern kept
    hits = vs.search(col, "what is a quadratic?", top_k=5)

The `_Collection` handle returned by `get_or_create_collection` is a
thin dataclass holding the tenant id and collection name. Everything
else lives in the `ContentEmbedding` table.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from django.db import transaction

logger = logging.getLogger(__name__)


@dataclass
class _Collection:
    """Thin stand-in for ChromaDB's Collection. Only carries routing info."""
    tenant_id: str
    name: str
    _client: 'VectorStoreClient'

    def delete(self, ids: List[str]) -> None:
        """Chroma-compatible shim: delete embeddings by their embedding_id."""
        self._client.delete_documents(self, ids)

    def count(self) -> int:
        return self._client._count(self)

    def peek(self, limit: int = 3) -> Dict:
        ids = list(
            self._client._queryset(self)
            .order_by('id')
            .values_list('embedding_id', flat=True)[:limit]
        )
        return {'ids': ids}


class VectorStoreClient:
    """pgvector adapter with a ChromaDB-compatible facade."""

    def __init__(self):
        self._embedding_service = None

    # ------------------------------------------------------------------ embedder

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            from clients.embeddings import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    # ------------------------------------------------------------------ collections

    def get_or_create_collection(self, tenant_id: str, name: str = 'curriculum') -> _Collection:
        """There is no physical collection in pgvector — just a routing handle.

        `tenant_id` is used as the `ContentEmbedding.tenant_id` filter on
        every query. `name` is carried through for diagnostics but has
        no DB meaning (single collection per tenant for now).
        """
        return _Collection(tenant_id=str(tenant_id), name=name, _client=self)

    # ------------------------------------------------------------------ writes

    @transaction.atomic
    def add_documents(
        self,
        collection: _Collection,
        documents: List[str],
        metadatas: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ) -> int:
        """Embed the batch and upsert a `ContentEmbedding` per text.

        Requires each metadata dict to carry `document_id` and `node_id`
        so we can resolve the underlying `ContentNode`. This matches
        exactly what `seed_synthetic_data._embed_tenant_nodes` emits.
        Returns number of rows persisted.
        """
        if not documents:
            return 0

        metadatas = metadatas or [{}] * len(documents)
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in documents]

        from apps.service.models import ContentEmbedding, ContentNode, EMBEDDING_DIM
        from django.conf import settings as dj_settings

        model_name = getattr(dj_settings, 'EMBEDDING_MODEL_NAME', 'all-MiniLM-L6-v2')

        # Bulk-embed the whole batch in one remote call.
        vectors = self.embedding_service.embed_batch(documents)
        if vectors and len(vectors[0]) != EMBEDDING_DIM:
            raise ValueError(
                f'Embedder returned dim={len(vectors[0])} but schema expects {EMBEDDING_DIM}. '
                f'Check that EMBEDDING_MODEL_NAME matches the embedder Space model.'
            )

        # Bulk-fetch the ContentNodes for this batch by (document_id, node_id).
        from django.db.models import Q
        q = Q()
        for meta in metadatas:
            doc_id = meta.get('document_id')
            node_id = meta.get('node_id')
            if doc_id and node_id:
                q |= Q(document_id=doc_id, node_id=node_id)

        node_lookup = {
            (n.document_id, n.node_id): n
            for n in ContentNode.objects.filter(tenant_id=collection.tenant_id).filter(q)
        }

        # Upsert: delete existing rows for this batch (via unique key),
        # then bulk-insert fresh ones. This gives us clean re-embedding
        # semantics without relying on PG's ON CONFLICT plumbing.
        node_ids_in_batch = [n.id for n in node_lookup.values()]
        ContentEmbedding.objects.filter(
            tenant_id=collection.tenant_id,
            content_node_id__in=node_ids_in_batch,
            model_name=model_name,
        ).delete()

        rows_to_create = []
        for doc, meta, eid, vec in zip(documents, metadatas, ids, vectors):
            node = node_lookup.get((meta.get('document_id'), meta.get('node_id')))
            if node is None:
                logger.debug(
                    'Skipping embedding: no ContentNode for doc=%s node=%s',
                    meta.get('document_id'), meta.get('node_id'),
                )
                continue
            rows_to_create.append(ContentEmbedding(
                tenant_id=collection.tenant_id,
                content_node=node,
                embedding=vec,
                model_name=model_name,
                embedding_id=eid,
            ))

        if rows_to_create:
            ContentEmbedding.objects.bulk_create(rows_to_create, batch_size=128)

        logger.info(
            'Added %d embeddings to tenant=%s (collection=%s, model=%s)',
            len(rows_to_create), collection.tenant_id, collection.name, model_name,
        )
        return len(rows_to_create)

    # ------------------------------------------------------------------ reads

    def search(
        self,
        collection: _Collection,
        query: str,
        top_k: int = 5,
    ) -> List[Dict]:
        """Cosine-distance top-k over the tenant's ContentEmbeddings."""
        if not query or not query.strip():
            return []

        from apps.service.models import ContentEmbedding
        from pgvector.django import CosineDistance

        query_vec = self.embedding_service.embed_text(query)

        rows = (
            ContentEmbedding.objects
            .filter(tenant_id=collection.tenant_id)
            .annotate(distance=CosineDistance('embedding', query_vec))
            .order_by('distance')
            .select_related('content_node__document')[:top_k]
        )

        hits = []
        for row in rows:
            node = row.content_node
            hits.append({
                'text': node.content_plain or node.content or '',
                'metadata': {
                    'tenant_id': collection.tenant_id,
                    'document_id': node.document_id,
                    'node_id': node.node_id,
                    'node_type': node.node_type,
                    'subject_id': node.subject_id,
                    'difficulty': node.difficulty or '',
                    'title': node.title,
                },
                'score': 1.0 - float(row.distance),  # cosine similarity, 0..1
            })
        return hits

    # ------------------------------------------------------------------ admin / housekeeping

    def delete_documents(self, collection: _Collection, ids: List[str]) -> None:
        """Delete by embedding_id (legacy Chroma-style identifier)."""
        if not ids:
            return
        deleted, _ = (
            self._queryset(collection)
            .filter(embedding_id__in=ids)
            .delete()
        )
        logger.info("Deleted %d embeddings from tenant=%s", deleted, collection.tenant_id)

    def get_collection_stats(self, collection: _Collection) -> Dict:
        count = self._count(collection)
        peek = collection.peek(limit=3)
        return {
            'name': f'{collection.tenant_id}_{collection.name}',
            'count': count,
            'sample_ids': peek['ids'],
        }

    def list_collections(self) -> List[str]:
        """Return `<tenant_id>_curriculum` strings for every tenant with embeddings."""
        from apps.service.models import ContentEmbedding
        tenant_ids = (
            ContentEmbedding.objects
            .values_list('tenant_id', flat=True)
            .distinct()
        )
        return [f'{t}_curriculum' for t in tenant_ids]

    def delete_collection(self, tenant_id: str, name: str = 'curriculum') -> None:
        """Delete every embedding belonging to a tenant."""
        from apps.service.models import ContentEmbedding
        deleted, _ = ContentEmbedding.objects.filter(tenant_id=str(tenant_id)).delete()
        logger.info("Deleted %d embeddings (tenant=%s, collection=%s)",
                    deleted, tenant_id, name)

    # ------------------------------------------------------------------ internals

    def _queryset(self, collection: _Collection):
        from apps.service.models import ContentEmbedding
        return ContentEmbedding.objects.filter(tenant_id=collection.tenant_id)

    def _count(self, collection: _Collection) -> int:
        return self._queryset(collection).count()
