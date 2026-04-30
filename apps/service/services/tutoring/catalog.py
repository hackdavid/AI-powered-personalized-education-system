"""
Student catalog — compact subject + top-level topic map used by the router.

The router needs to know, per student, *which subjects they can actually ask
about* and *what the top-level chapters look like* so the classifier LLM can
pick the right subject AND a plausible topic without the answerer having to
guess. We build that index once per (tenant, grade) and cache it.

Shape of the catalog:

    [
        {
            'subject_id': 12,
            'name': 'Mathematics',
            'code': 'MATH',
            'description': '',
            'chapters': [
                {'node_id': 'ch1', 'title': 'Number Systems'},
                {'node_id': 'ch2', 'title': 'Polynomials'},
                ...
            ],
        },
        ...
    ]

`chapters` is capped at `MAX_CHAPTERS_PER_SUBJECT` so the classifier prompt
stays small even when a book has 30+ chapters. That's fine for routing
because the classifier only needs to *recognise* the topic space — the
actual grounding happens later via pgvector on the full ContentNode set.

Cache key = (tenant_id, grade_level). Invalidate on Document ingestion
(hook in the ingestion pipeline; not done here to avoid churn).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)


# Prompt-size guardrails. Tune if routing accuracy drops on long curricula.
MAX_CHAPTERS_PER_SUBJECT = 25
MAX_SUBJECTS = 15
CACHE_TIMEOUT_SECONDS = 60 * 30  # 30 minutes


# --------------------------------------------------------------------------- dataclasses


@dataclass
class Chapter:
    node_id: str
    title: str

    def to_dict(self) -> dict:
        return {'node_id': self.node_id, 'title': self.title}


@dataclass
class SubjectCatalog:
    subject_id: int
    name: str
    code: str = ''
    description: str = ''
    chapters: List[Chapter] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'subject_id': self.subject_id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'chapters': [c.to_dict() for c in self.chapters],
        }

    @property
    def searchable_text(self) -> str:
        """Tiny string used for embedding-based subject ranking."""
        parts = [self.name]
        if self.code:
            parts.append(self.code)
        if self.description:
            parts.append(self.description)
        if self.chapters:
            parts.append(', '.join(c.title for c in self.chapters[:8]))
        return ' — '.join(parts)


# --------------------------------------------------------------------------- public API


def _cache_key(tenant_id, grade_level: Optional[int]) -> str:
    return f'tutor:catalog:{tenant_id}:{grade_level or 0}'


def get_student_catalog(student, *, use_cache: bool = True) -> List[SubjectCatalog]:
    """Return the subject + chapter index a student can ask about.

    Resolution order:
      1. Subjects that already have `ClassSubject` rows for a class in the
         student's grade_level (the strict, school-curriculum-backed answer).
      2. Fallback: every active subject in the tenant that has at least one
         published ContentNode. Used when grade_level isn't set or the
         school admin hasn't assigned ClassSubjects yet.
    """
    tenant_id = getattr(student, 'tenant_id', None)
    grade_level = getattr(student, 'grade_level', None)
    if not tenant_id:
        return []

    key = _cache_key(tenant_id, grade_level)
    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return [SubjectCatalog(**_hydrate(c)) for c in cached]

    catalog = _build_catalog(tenant_id=tenant_id, grade_level=grade_level)

    if use_cache:
        try:
            cache.set(key, [c.to_dict() for c in catalog], CACHE_TIMEOUT_SECONDS)
        except Exception as exc:  # cache layer may not be wired in tests
            logger.debug('catalog cache set failed: %s', exc)

    return catalog


def invalidate_catalog(tenant_id, grade_level: Optional[int] = None) -> None:
    """Clear the cached catalog. Call after an ingestion finishes.

    Passing `grade_level=None` clears the generic fallback entry. Call this
    plus the specific grade you changed to cover both hits.
    """
    cache.delete(_cache_key(tenant_id, grade_level))


# --------------------------------------------------------------------------- internals


def _hydrate(d: dict) -> dict:
    """Rebuild `Chapter` objects from the cached dict form."""
    out = dict(d)
    out['chapters'] = [Chapter(**c) for c in d.get('chapters', [])]
    return out


def _build_catalog(*, tenant_id, grade_level: Optional[int]) -> List[SubjectCatalog]:
    from apps.service.models import ClassSubject, ContentNode, Subject

    base_subjects_qs = Subject.objects.filter(tenant_id=tenant_id, is_active=True)

    # Prefer subjects actually assigned to a class at the student's grade.
    subjects: List[Subject] = []
    if grade_level is not None:
        linked_ids = (
            ClassSubject.objects
            .filter(
                class_obj__tenant_id=tenant_id,
                class_obj__grade_level=grade_level,
                is_active=True,
            )
            .values_list('subject_id', flat=True)
            .distinct()
        )
        subjects = list(base_subjects_qs.filter(id__in=linked_ids).order_by('name'))

    # Fallback: any active subject with ContentNodes. Keeps the tutor
    # useful before a school admin finishes wiring ClassSubjects.
    if not subjects:
        node_subject_ids = (
            ContentNode.objects
            .filter(tenant_id=tenant_id, subject_id__isnull=False)
            .values_list('subject_id', flat=True)
            .distinct()
        )
        subjects = list(base_subjects_qs.filter(id__in=node_subject_ids).order_by('name'))

    # Hard cap so the classifier prompt stays small.
    subjects = subjects[:MAX_SUBJECTS]
    if not subjects:
        return []

    # Bulk-fetch chapters (and sections, as many curricula skip explicit
    # 'chapter' nodes) for the selected subjects in one query.
    node_qs = (
        ContentNode.objects
        .filter(
            tenant_id=tenant_id,
            subject_id__in=[s.id for s in subjects],
            node_type__in=['chapter', 'section'],
        )
        .order_by('subject_id', 'document_id', 'position')
        .values('subject_id', 'node_id', 'title', 'node_type')
    )

    # Prefer chapters; pad with sections only if a subject has no chapters.
    grouped: dict[int, dict[str, List[Chapter]]] = {}
    for row in node_qs:
        bucket = grouped.setdefault(row['subject_id'], {'chapter': [], 'section': []})
        # Dedupe on (node_id, title) to avoid repeating nodes that exist in
        # multiple documents (intro Maths chapter in two different books).
        existing = bucket[row['node_type']]
        if not any(c.node_id == row['node_id'] and c.title == row['title'] for c in existing):
            existing.append(Chapter(node_id=row['node_id'], title=row['title']))

    catalog: List[SubjectCatalog] = []
    for s in subjects:
        buckets = grouped.get(s.id, {'chapter': [], 'section': []})
        chapters = buckets['chapter'] or buckets['section']
        catalog.append(SubjectCatalog(
            subject_id=s.id,
            name=s.name,
            code=s.code or '',
            description=(s.description or '').strip(),
            chapters=chapters[:MAX_CHAPTERS_PER_SUBJECT],
        ))
    return catalog
