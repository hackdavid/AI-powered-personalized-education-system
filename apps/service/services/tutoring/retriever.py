"""
Curriculum retriever — subject-scoped pgvector search with topic-aware reranking.

Talks to `ContentEmbedding` directly via the ORM so we can push the router's
subject filter down into the same query that does the cosine search. That's
cheaper *and* more accurate than the old "retrieve top-k globally, filter in
Python" flow: we no longer throw away high-similarity hits just because they
belong to the wrong subject for this question.

Query shape:

    ContentEmbedding.objects
        .filter(tenant=tenant, model_name=EMBEDDING_MODEL_NAME,
                content_node__subject_id__in=subject_ids)   # if routed
        .annotate(distance=CosineDistance('embedding', qv))
        .order_by('distance')
        .select_related('content_node__document')[:top_k * retrieve_multiplier]

We retrieve more than `top_k` when `topic_titles` is non-empty and rerank
locally with a tiny title-match boost. This is cheap and gives a meaningful
precision lift for multi-topic subjects (e.g. a question about *polynomials*
inside Mathematics gets polynomial chunks ahead of algebra ones).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

from django.conf import settings

from apps.accounts.models import Tenant

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
    subject_name: str = ''
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _trim(text: str, length: int = 600) -> str:
    if not text:
        return ''
    text = text.strip()
    return text if len(text) <= length else text[: length - 1] + '…'


# A small over-fetch so we have room to rerank locally when topic_titles is set.
RETRIEVE_MULTIPLIER = 3
TOPIC_MATCH_BOOST = 0.08


class CurriculumRetriever:
    """Retrieve grounded curriculum chunks, optionally scoped by subject."""

    COLLECTION_NAME = 'curriculum'

    def __init__(self, embedding_service=None):
        self._embedding_service = embedding_service

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            from clients.embeddings import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    # ------------------------------------------------------------------ public

    def retrieve(
        self,
        tenant: Tenant,
        query: str,
        *,
        top_k: int = 5,
        subject_ids: Optional[Sequence[int]] = None,
        topic_titles: Optional[Sequence[str]] = None,
        # Back-compat with the old single-subject signature. Ignored when
        # `subject_ids` is provided (caller went with the new API).
        subject_id: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Return up to `top_k` chunks for `query`.

        `subject_ids` applies a hard DB-level filter via the `ContentNode.subject`
        join. `topic_titles` softly boosts matching nodes' scores after the
        pgvector sort, which is enough for the multi-topic case without
        hurting recall.
        """
        query = (query or '').strip()
        if not query:
            return []

        scope_ids = list(subject_ids) if subject_ids else None
        if scope_ids is None and subject_id is not None:
            scope_ids = [subject_id]

        try:
            query_vec = self.embedding_service.embed_text(query)
        except Exception as exc:
            logger.warning('retriever: embedding failed for tenant=%s: %s', tenant.id, exc)
            return []

        try:
            raw_hits = self._pgvector_search(
                tenant=tenant,
                query_vec=query_vec,
                top_k=top_k,
                subject_ids=scope_ids,
            )
        except Exception as exc:
            logger.warning(
                'retriever: pgvector query failed for tenant=%s (subjects=%s): %s',
                tenant.id, scope_ids, exc,
            )
            return []

        # Rerank with topic match if the router gave us titles.
        reranked = self._rerank_by_topic(raw_hits, topic_titles)
        return reranked[:top_k]

    # ------------------------------------------------------------------ internals

    def _pgvector_search(
        self,
        *,
        tenant: Tenant,
        query_vec,
        top_k: int,
        subject_ids: Optional[Sequence[int]],
    ) -> List[RetrievedChunk]:
        """Run the actual cosine-distance ordered query."""
        from pgvector.django import CosineDistance

        from apps.service.models import ContentEmbedding

        model_name = getattr(settings, 'EMBEDDING_MODEL_NAME', 'all-MiniLM-L6-v2')
        limit = max(top_k * RETRIEVE_MULTIPLIER, top_k)

        qs = (
            ContentEmbedding.objects
            .filter(tenant=tenant, model_name=model_name)
            .annotate(distance=CosineDistance('embedding', query_vec))
            .order_by('distance')
            .select_related('content_node__document', 'content_node__subject')
        )
        if subject_ids:
            qs = qs.filter(content_node__subject_id__in=list(subject_ids))

        rows = qs[:limit]

        out: List[RetrievedChunk] = []
        for row in rows:
            node = row.content_node
            if node is None:
                continue  # orphaned embedding
            document = node.document
            subject = node.subject

            out.append(RetrievedChunk(
                node_id=node.node_id,
                document_id=node.document_id,
                document_title=document.title if document else '',
                title=node.title,
                snippet=_trim(node.content_plain or node.content or ''),
                score=float(1.0 - row.distance),  # cosine similarity in [0,1]
                page_number=node.page_number,
                subject_id=node.subject_id,
                subject_name=subject.name if subject else '',
                extra={
                    'node_type': node.node_type,
                    'difficulty': node.difficulty or '',
                },
            ))
        return out

    @staticmethod
    def _rerank_by_topic(
        hits: List[RetrievedChunk],
        topic_titles: Optional[Sequence[str]],
    ) -> List[RetrievedChunk]:
        """Boost chunks whose title matches the router's topic picks.

        Substring match both ways (topic ⊂ node, node ⊂ topic) so small
        wording differences don't sink an otherwise perfect chunk.
        """
        if not hits or not topic_titles:
            return hits

        titles_lower = [t.lower() for t in topic_titles if t]
        if not titles_lower:
            return hits

        boosted: List[RetrievedChunk] = []
        for h in hits:
            boost = 0.0
            node_title_lower = (h.title or '').lower()
            for topic in titles_lower:
                if topic and (topic in node_title_lower or node_title_lower in topic):
                    boost = TOPIC_MATCH_BOOST
                    break
            if boost:
                boosted.append(RetrievedChunk(
                    node_id=h.node_id,
                    document_id=h.document_id,
                    document_title=h.document_title,
                    title=h.title,
                    snippet=h.snippet,
                    score=h.score + boost,
                    page_number=h.page_number,
                    subject_id=h.subject_id,
                    subject_name=h.subject_name,
                    extra={**h.extra, 'topic_boosted': True},
                ))
            else:
                boosted.append(h)

        boosted.sort(key=lambda c: c.score, reverse=True)
        return boosted
