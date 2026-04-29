"""
Curriculum retriever — thin wrapper over `clients.vector_store.VectorStoreClient`.

Retrieves the top-k most relevant ContentNode chunks for a query, scoped to a
tenant's `<tenant_id>_curriculum` collection. Returned hits are enriched with
the matching `ContentNode` row so callers (and the chat UI) can render proper
citations: title, document, page number, and the local node path.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from django.conf import settings

from apps.accounts.models import Tenant
from apps.service.models import ContentNode

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """One source chunk surfaced to the LLM and to the UI."""
    node_id: str
    document_id: int
    document_title: str
    title: str
    snippet: str
    score: float
    page_number: Optional[int] = None
    subject_id: Optional[int] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _trim(text: str, length: int = 600) -> str:
    if not text:
        return ''
    text = text.strip()
    return text if len(text) <= length else text[: length - 1] + '…'


class CurriculumRetriever:
    """Retrieve grounded curriculum chunks for a tenant."""

    COLLECTION_NAME = 'curriculum'

    def __init__(self, vector_store=None):
        self._vector_store = vector_store

    @property
    def vector_store(self):
        if self._vector_store is None:
            from clients.vector_store import VectorStoreClient
            self._vector_store = VectorStoreClient()
        return self._vector_store

    def retrieve(
        self,
        tenant: Tenant,
        query: str,
        top_k: int = 5,
        subject_id: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Return up to `top_k` chunks for `query` from the tenant's curriculum."""
        if not query.strip():
            return []

        try:
            collection = self.vector_store.get_or_create_collection(
                str(tenant.id),
                self.COLLECTION_NAME,
            )
            hits = self.vector_store.search(collection, query, top_k=top_k)
        except Exception as exc:
            # Vector store / embeddings unavailable. Log and return empty;
            # the tutor will then say it has no sources rather than hard-erroring.
            logger.warning(
                'Vector store retrieval failed for tenant=%s query=%r: %s',
                tenant.id, query[:60], exc,
            )
            return []

        return self._enrich_hits(tenant, hits, subject_id=subject_id)

    def _enrich_hits(
        self,
        tenant: Tenant,
        hits: List[dict],
        subject_id: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Merge each hit with its underlying ContentNode row for full citations."""
        if not hits:
            return []

        # Pull (document_id, node_id) pairs from metadata so we can do a single bulk lookup.
        keys = []
        for h in hits:
            meta = h.get('metadata') or {}
            doc_id = meta.get('document_id')
            node_id = meta.get('node_id')
            if doc_id is None or node_id is None:
                continue
            keys.append((doc_id, node_id))

        if not keys:
            return []

        # Bulk fetch matching ContentNodes for this tenant.
        from django.db.models import Q
        q = Q()
        for doc_id, node_id in keys:
            q |= Q(document_id=doc_id, node_id=node_id)

        node_qs = ContentNode.objects.filter(tenant=tenant).filter(q).select_related('document')
        node_lookup = {(n.document_id, n.node_id): n for n in node_qs}

        out: List[RetrievedChunk] = []
        for h in hits:
            meta = h.get('metadata') or {}
            doc_id = meta.get('document_id')
            node_id = meta.get('node_id')
            node = node_lookup.get((doc_id, node_id))
            if node is None:
                # Vector hit no longer matches an ORM row — skip silently.
                continue
            if subject_id and node.subject_id and node.subject_id != subject_id:
                continue

            out.append(RetrievedChunk(
                node_id=node.node_id,
                document_id=node.document_id,
                document_title=node.document.title if node.document_id else '',
                title=node.title,
                snippet=_trim(h.get('text') or node.content_plain or ''),
                score=float(h.get('score') or 0.0),
                page_number=node.page_number,
                subject_id=node.subject_id,
                extra={'node_type': node.node_type},
            ))
        return out
