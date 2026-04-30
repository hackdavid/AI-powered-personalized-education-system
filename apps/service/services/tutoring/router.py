"""
Query router — picks subject + topics + intent for a student question.

The router is the "first hop" of the dynamic tutor pipeline. It replaces the
old modal where the student had to choose a subject before chatting:

    student.query --embedding--> top-N candidate subjects
                 --one LLM call--> Routing(subject, topics, intent, refined)
                 --pgvector------> grounded chunks (filtered by subject)
                 --answer LLM----> final streamed Markdown answer

We do exactly **one** classifier LLM call, with:

  * JSON mode (`response_format={"type":"json_object"}`), temperature=0
  * The same model as the answerer (project rule: single LLM for everything)
  * A compact prompt: only the top-N candidate subjects with their chapters
    (pre-ranked by embedding cosine) — not the whole curriculum

Failure modes and what we do about them:

  * LLM endpoint unreachable   → keep the embedding-only ranking as routing
  * LLM returns broken JSON    → same fallback
  * No catalog yet (fresh tenant) → route everywhere, skip filter

The public entry point is `QueryRouter.route(...)`. It's pure — no DB writes —
so tests can exercise it with fake catalogs and mocked LLM.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .catalog import SubjectCatalog

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- config


# How many candidate subjects we pass to the classifier prompt. Keeping this
# small makes the prompt cheap and raises accuracy for the LLM's final pick.
CANDIDATE_SUBJECTS = 4

# Intents the classifier is allowed to return. Kept short on purpose; the UI
# uses these to pick an icon / skip retrieval for chitchat.
ALLOWED_INTENTS = (
    'concept_explanation',
    'problem_solving',
    'definition',
    'example_request',
    'summary_request',
    'chitchat',
    'meta',  # "who are you", "what can you do"
    'other',
)


# --------------------------------------------------------------------------- result type


@dataclass
class Routing:
    """What the router hands back to TutorService."""

    subject_ids: List[int] = field(default_factory=list)
    subject_names: List[str] = field(default_factory=list)
    topic_titles: List[str] = field(default_factory=list)
    refined_query: str = ''
    intent: str = 'other'
    needs_retrieval: bool = True
    # Diagnostics: LLM confidence (if provided) and raw candidates.
    confidence: float = 0.0
    candidate_subject_ids: List[int] = field(default_factory=list)
    source: str = 'llm'  # 'llm' | 'embedding' | 'heuristic'

    def to_dict(self) -> dict:
        return {
            'subject_ids': self.subject_ids,
            'subject_names': self.subject_names,
            'topic_titles': self.topic_titles,
            'refined_query': self.refined_query,
            'intent': self.intent,
            'needs_retrieval': self.needs_retrieval,
            'confidence': self.confidence,
            'candidate_subject_ids': self.candidate_subject_ids,
            'source': self.source,
        }


# --------------------------------------------------------------------------- embedding rank


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Plain cosine similarity. Returns 0 on zero-norm vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def rank_subjects_by_embedding(
    query: str,
    catalog: Sequence[SubjectCatalog],
    embedding_service=None,
    *,
    top_n: int = CANDIDATE_SUBJECTS,
) -> List[SubjectCatalog]:
    """Return `catalog` reordered by cosine of `query` against each subject.

    Falls back to the catalog's natural order (alphabetical) if the embedder
    misbehaves. This is the fastest path to reasonable routing and is what
    we use as the safety net when the classifier LLM fails.
    """
    if not catalog:
        return []

    if embedding_service is None:
        try:
            from clients.embeddings import get_embedding_service
            embedding_service = get_embedding_service()
        except Exception as exc:
            logger.debug('embedding service unavailable: %s', exc)
            return list(catalog)[:top_n]

    try:
        query_vec = embedding_service.embed_text(query)
        subject_texts = [s.searchable_text for s in catalog]
        subject_vecs = embedding_service.embed_batch(subject_texts)
    except Exception as exc:
        logger.debug('embedding ranking failed: %s', exc)
        return list(catalog)[:top_n]

    scored = [
        (_cosine(query_vec, vec), s)
        for vec, s in zip(subject_vecs, catalog)
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [s for _, s in scored[:top_n]]


# --------------------------------------------------------------------------- classifier prompt


_CLASSIFIER_SYSTEM = (
    "You are a routing layer for an AI tutor built for school students. "
    "You do NOT answer the question. Your only job is to decide which "
    "subject(s) and chapter(s) the question belongs to, rewrite the query "
    "so it is clean and retrieval-friendly, and flag the intent. Respond "
    "with STRICT JSON only — no prose, no markdown fences."
)


def _render_catalog_for_prompt(candidates: Sequence[SubjectCatalog]) -> str:
    lines = []
    for s in candidates:
        header = f'- id={s.subject_id} name="{s.name}"'
        if s.code:
            header += f' code="{s.code}"'
        lines.append(header)
        if s.description:
            lines.append(f'  description: {s.description[:140]}')
        if s.chapters:
            titles = '; '.join(c.title for c in s.chapters[:12])
            lines.append(f'  chapters: {titles}')
    return '\n'.join(lines)


def _build_classifier_prompt(
    query: str,
    candidates: Sequence[SubjectCatalog],
    grade_level: Optional[int],
    history_snippet: str,
) -> str:
    catalog_block = _render_catalog_for_prompt(candidates)
    grade_line = f'Grade level: {grade_level}\n' if grade_level else ''
    history_block = f'Recent conversation (for pronoun / follow-up resolution):\n{history_snippet}\n\n' if history_snippet else ''

    schema_example = (
        '{\n'
        '  "subject_ids": [12],                  // one or more ids from the catalog above\n'
        '  "topic_titles": ["Quadratic Equations"], // 0-3 chapter titles copied verbatim\n'
        '  "refined_query": "...",               // rephrase user question; expand pronouns\n'
        '  "intent": "concept_explanation",      // one of: '
        + ', '.join(ALLOWED_INTENTS) + '\n'
        '  "needs_retrieval": true,              // false for chitchat / meta\n'
        '  "confidence": 0.0-1.0                 // your confidence in the subject pick\n'
        '}'
    )

    return (
        f'{grade_line}'
        f'Candidate subjects (already filtered to the top-{len(candidates)} most likely for this query):\n'
        f'{catalog_block}\n\n'
        f'{history_block}'
        f'Student question:\n"{query}"\n\n'
        'Decide which subject(s) and topic(s) this question belongs to.\n'
        'Rules:\n'
        ' - subject_ids must be a subset of the ids listed above. If none fits, return [].\n'
        ' - topic_titles must be copied verbatim from the chapters list (or []).\n'
        ' - Set needs_retrieval=false only for chitchat (hello, thanks) or tutor-meta questions.\n'
        ' - refined_query should resolve pronouns and vague references using the conversation history when present.\n'
        ' - Output ONLY valid JSON matching this shape:\n'
        f'{schema_example}'
    )


# --------------------------------------------------------------------------- main router


class QueryRouter:
    """Single-LLM-call classifier with embedding-based safety net."""

    def __init__(self, llm_service=None, embedding_service=None):
        self._llm = llm_service
        self._embedding = embedding_service

    @property
    def llm(self):
        if self._llm is None:
            from clients.llm import LLMService
            self._llm = LLMService()
        return self._llm

    # ------------------------------------------------------------------ public

    def route(
        self,
        query: str,
        catalog: Sequence[SubjectCatalog],
        *,
        grade_level: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Routing:
        query = (query or '').strip()
        if not query:
            return Routing(refined_query='', intent='other', needs_retrieval=False, source='heuristic')

        if not catalog:
            # No curriculum yet — retrieve anyway, unfiltered.
            return Routing(refined_query=query, intent='other', needs_retrieval=True, source='heuristic')

        candidates = rank_subjects_by_embedding(
            query,
            catalog,
            embedding_service=self._embedding,
            top_n=CANDIDATE_SUBJECTS,
        )
        candidate_ids = [c.subject_id for c in candidates]

        # Try the classifier LLM first — it understands intent + topic pick.
        routing = self._classify_with_llm(
            query=query,
            candidates=candidates,
            grade_level=grade_level,
            history=history,
        )
        if routing is not None:
            routing.candidate_subject_ids = candidate_ids
            routing.source = 'llm'
            return self._sanitize(routing, candidates, fallback_query=query)

        # Fallback: trust the embedding ranking; keep top-1 subject.
        logger.info('router: LLM classifier unavailable, falling back to embedding ranking')
        top = candidates[0]
        return Routing(
            subject_ids=[top.subject_id],
            subject_names=[top.name],
            topic_titles=[],
            refined_query=query,
            intent='other',
            needs_retrieval=True,
            confidence=0.0,
            candidate_subject_ids=candidate_ids,
            source='embedding',
        )

    # ------------------------------------------------------------------ internals

    def _classify_with_llm(
        self,
        *,
        query: str,
        candidates: Sequence[SubjectCatalog],
        grade_level: Optional[int],
        history: Optional[List[Dict[str, str]]],
    ) -> Optional[Routing]:
        if not self.llm.is_configured:
            return None

        history_snippet = _compact_history(history)
        prompt = _build_classifier_prompt(query, candidates, grade_level, history_snippet)

        try:
            raw = self.llm.generate_structured(
                prompt=prompt,
                system=_CLASSIFIER_SYSTEM,
                temperature=0.0,
                max_tokens=400,
            )
        except Exception as exc:
            logger.warning('router classifier errored: %s', exc)
            return None
        if not raw:
            return None

        try:
            subject_ids = [int(x) for x in (raw.get('subject_ids') or []) if _looks_like_int(x)]
            topic_titles = [str(x).strip() for x in (raw.get('topic_titles') or []) if x]
            refined_query = (raw.get('refined_query') or query).strip()
            intent = (raw.get('intent') or 'other').strip().lower()
            if intent not in ALLOWED_INTENTS:
                intent = 'other'
            needs_retrieval = bool(raw.get('needs_retrieval', True))
            confidence = float(raw.get('confidence') or 0.0)
        except (TypeError, ValueError) as exc:
            logger.debug('router: malformed JSON from classifier: %s', exc)
            return None

        return Routing(
            subject_ids=subject_ids,
            topic_titles=topic_titles,
            refined_query=refined_query,
            intent=intent,
            needs_retrieval=needs_retrieval,
            confidence=confidence,
        )

    def _sanitize(
        self,
        routing: Routing,
        candidates: Sequence[SubjectCatalog],
        *,
        fallback_query: str,
    ) -> Routing:
        """Clamp classifier output to what's actually in the catalog."""
        allowed_ids = {c.subject_id for c in candidates}
        name_by_id = {c.subject_id: c.name for c in candidates}
        allowed_titles = {
            chapter.title.lower()
            for c in candidates
            for chapter in c.chapters
        }

        # Drop subject ids that don't exist in the candidate pool (LLM hallucination).
        filtered_subjects = [sid for sid in routing.subject_ids if sid in allowed_ids]

        # If the classifier returned nothing usable, surrender to the top-1 embedding candidate.
        if not filtered_subjects and routing.needs_retrieval and candidates:
            filtered_subjects = [candidates[0].subject_id]

        subject_names = [name_by_id[sid] for sid in filtered_subjects if sid in name_by_id]

        # Keep only topic titles the catalog actually contains (case-insensitive).
        filtered_topics = [t for t in routing.topic_titles if t.lower() in allowed_titles]

        refined = routing.refined_query.strip() or fallback_query

        return Routing(
            subject_ids=filtered_subjects,
            subject_names=subject_names,
            topic_titles=filtered_topics,
            refined_query=refined,
            intent=routing.intent,
            needs_retrieval=routing.needs_retrieval,
            confidence=routing.confidence,
            candidate_subject_ids=routing.candidate_subject_ids,
            source=routing.source,
        )


# --------------------------------------------------------------------------- helpers


def _looks_like_int(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _compact_history(history: Optional[List[Dict[str, str]]], max_turns: int = 4) -> str:
    """Fold the last few turns into a short text block for the classifier.

    The classifier benefits from pronoun context ("Explain it again like
    I'm five") but doesn't need the whole thread. We take the last
    `max_turns` messages, trim each, and format as simple role tags.
    """
    if not history:
        return ''
    tail = history[-max_turns:]
    lines = []
    for turn in tail:
        role = turn.get('role', 'user')
        content = (turn.get('content') or '').strip().replace('\n', ' ')
        if len(content) > 200:
            content = content[:197] + '...'
        if content:
            lines.append(f'{role}: {content}')
    return '\n'.join(lines)
