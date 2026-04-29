"""
Book seeding from YAML fixtures.

Each YAML file under `fixtures/synthetic_books/` declares one book.
This module:
  1. Reads + validates each YAML.
  2. Creates / updates a `Document` row per `(tenant, slug)`.
  3. Builds the ContentNode tree (chapter -> section -> topic -> leaves).
  4. Resolves cross_refs into ContentCrossRef rows.

Idempotent: re-running with the same YAML produces the same row counts.
The reset flag is handled at the orchestration layer (the management
command), not here, so callers can reseed users without rebuilding books.
"""

import re
from pathlib import Path
from typing import Dict, Iterable, List

import yaml

from django.conf import settings
from django.db import transaction

from apps.accounts.models import Tenant, User
from apps.service.models import (
    ContentCrossRef,
    ContentNode,
    Document,
    Subject,
)


VALID_LEAF_TYPES = {
    'definition', 'formula', 'example', 'exercise', 'summary', 'key_point'
}
VALID_REF_TYPES = {'prerequisite', 'related', 'extends', 'applies'}
VALID_DIFFICULTY = {'basic', 'intermediate', 'advanced', None, ''}


def default_books_dir() -> Path:
    return Path(settings.BASE_DIR) / 'fixtures' / 'synthetic_books'


def discover_book_files(root: Path | None = None) -> List[Path]:
    root = root or default_books_dir()
    if not root.exists():
        return []
    return sorted(p for p in root.glob('*.yaml'))


def load_book_yaml(path: Path) -> Dict:
    """Load and lightly validate a book YAML file."""
    with path.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    required = ['slug', 'title', 'subject_code', 'subject_name', 'grade_level']
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"{path.name}: missing required keys: {missing}")

    if not isinstance(data.get('chapters', []), list):
        raise ValueError(f"{path.name}: 'chapters' must be a list")

    return data


def _slug_to_node_id(slug: str) -> str:
    """Sanitize a YAML node slug to fit ContentNode.node_id (max 50 chars)."""
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', slug).strip('-')
    return s[:50]


def _ensure_subject(tenant: Tenant, code: str, name: str) -> Subject:
    """
    Return the Subject row for `(tenant, code)`. Creates it lazily if a
    book references a subject that wasn't pre-seeded by classes.py.
    """
    subject, _ = Subject.objects.get_or_create(
        tenant=tenant,
        code=code,
        defaults={'name': name, 'is_active': True},
    )
    return subject


def _normalize_difficulty(value: str | None) -> str | None:
    if value in VALID_DIFFICULTY:
        return value or None
    return None  # silently drop invalid values


@transaction.atomic
def _build_book(
    tenant: Tenant,
    book: Dict,
    created_by: User | None = None,
) -> Dict:
    """Build / refresh a single Document and its ContentNode tree."""

    subject = _ensure_subject(tenant, book['subject_code'], book['subject_name'])

    document, doc_created = Document.objects.get_or_create(
        tenant=tenant,
        title=book['title'],
        source_type=Document.SourceType.SYNTHETIC,
        defaults={
            'description': book.get('summary', ''),
            'subject': subject,
            'status': Document.Status.COMPLETED,
            'file_type': 'md',
            'created_by': created_by,
            'updated_by': created_by,
        },
    )

    # Always wipe + rebuild the ContentNode tree for the book; this keeps
    # the YAML the source of truth and avoids stale orphan nodes when
    # authors edit the file. ContentCrossRef rows cascade via FK.
    document.content_nodes.all().delete()

    counts = {
        'document_created': doc_created,
        'chapters': 0,
        'sections': 0,
        'topics': 0,
        'leaves': 0,
        'cross_refs': 0,
    }
    node_index: Dict[str, ContentNode] = {}  # node_id -> node (for cross_refs)

    book_difficulty = _normalize_difficulty(book.get('difficulty'))
    book_meta_base = {
        'book_slug': book['slug'],
        'grade_level': book['grade_level'],
    }

    for ch_pos, chapter in enumerate(book.get('chapters', []), start=1):
        ch_id = _slug_to_node_id(f"ch{ch_pos}")
        ch_node = ContentNode.objects.create(
            tenant=tenant,
            document=document,
            parent=None,
            subject=subject,
            node_id=ch_id,
            node_type='chapter',
            title=chapter.get('title', f'Chapter {ch_pos}'),
            content=chapter.get('content', '') or '',
            content_plain=chapter.get('content', '') or '',
            page_number=chapter.get('page_number'),
            difficulty=_normalize_difficulty(chapter.get('difficulty')) or book_difficulty,
            position=chapter.get('position', ch_pos),
            metadata={**book_meta_base, 'path': ch_id},
        )
        node_index[ch_id] = ch_node
        counts['chapters'] += 1

        for sec_pos, section in enumerate(chapter.get('sections', []), start=1):
            sec_id = _slug_to_node_id(f"{ch_id}.s{sec_pos}")
            sec_node = ContentNode.objects.create(
                tenant=tenant,
                document=document,
                parent=ch_node,
                subject=subject,
                node_id=sec_id,
                node_type='section',
                title=section.get('title', f'Section {sec_pos}'),
                content=section.get('content', '') or '',
                content_plain=section.get('content', '') or '',
                page_number=section.get('page_number'),
                difficulty=_normalize_difficulty(section.get('difficulty')) or ch_node.difficulty,
                position=section.get('position', sec_pos),
                metadata={**book_meta_base, 'path': sec_id},
            )
            node_index[sec_id] = sec_node
            counts['sections'] += 1

            for top_pos, topic in enumerate(section.get('topics', []), start=1):
                top_id = _slug_to_node_id(f"{sec_id}.t{top_pos}")
                content_md = topic.get('content', '') or ''
                top_node = ContentNode.objects.create(
                    tenant=tenant,
                    document=document,
                    parent=sec_node,
                    subject=subject,
                    node_id=top_id,
                    node_type='topic',
                    title=topic.get('title', f'Topic {top_pos}'),
                    content=content_md,
                    content_plain=content_md,
                    page_number=topic.get('page_number'),
                    difficulty=_normalize_difficulty(topic.get('difficulty')) or sec_node.difficulty,
                    position=topic.get('position', top_pos),
                    metadata={**book_meta_base, 'path': top_id},
                )
                node_index[top_id] = top_node
                counts['topics'] += 1

                for leaf_pos, leaf in enumerate(topic.get('leaves', []), start=1):
                    leaf_type = leaf.get('type', 'key_point')
                    if leaf_type not in VALID_LEAF_TYPES:
                        leaf_type = 'key_point'
                    leaf_id = _slug_to_node_id(f"{top_id}.l{leaf_pos}")
                    leaf_md = leaf.get('content', '') or ''
                    leaf_node = ContentNode.objects.create(
                        tenant=tenant,
                        document=document,
                        parent=top_node,
                        subject=subject,
                        node_id=leaf_id,
                        node_type=leaf_type,
                        title=leaf.get('title', leaf_type.title()),
                        content=leaf_md,
                        content_plain=leaf_md,
                        page_number=leaf.get('page_number'),
                        difficulty=_normalize_difficulty(leaf.get('difficulty')) or top_node.difficulty,
                        position=leaf.get('position', leaf_pos),
                        metadata={**book_meta_base, 'path': leaf_id},
                    )
                    node_index[leaf_id] = leaf_node
                    counts['leaves'] += 1

    # Cross references (resolved via node_id lookup)
    for ref in book.get('cross_refs', []) or []:
        src = node_index.get(_slug_to_node_id(ref.get('source_path', '')))
        tgt = node_index.get(_slug_to_node_id(ref.get('target_path', '')))
        ref_type = ref.get('ref_type')
        if not src or not tgt or ref_type not in VALID_REF_TYPES:
            continue
        if src.tenant_id != tgt.tenant_id:
            continue
        ContentCrossRef.objects.get_or_create(
            tenant=tenant,
            source_node=src,
            target_node=tgt,
            ref_type=ref_type,
            defaults={'description': ref.get('description', '')},
        )
        counts['cross_refs'] += 1

    return {
        'document': document,
        'counts': counts,
    }


def seed_books(
    tenant: Tenant,
    book_files: Iterable[Path] | None = None,
    created_by: User | None = None,
) -> Dict:
    """Build all synthetic books under `fixtures/synthetic_books/` for a tenant."""
    book_files = list(book_files) if book_files else discover_book_files()

    summary = {
        'books_processed': 0,
        'documents_created': 0,
        'documents_updated': 0,
        'chapters': 0,
        'sections': 0,
        'topics': 0,
        'leaves': 0,
        'cross_refs': 0,
        'documents': [],
    }

    for path in book_files:
        book = load_book_yaml(path)
        result = _build_book(tenant, book, created_by=created_by)
        c = result['counts']
        summary['books_processed'] += 1
        if c['document_created']:
            summary['documents_created'] += 1
        else:
            summary['documents_updated'] += 1
        for key in ('chapters', 'sections', 'topics', 'leaves', 'cross_refs'):
            summary[key] += c[key]
        summary['documents'].append(result['document'])

    return summary
