"""Student-facing Codex — browseable curriculum atlas.

Three views:
- `codex_list_view`      — all subjects for the student's tenant, with
  chapter counts, clickable into each subject.
- `codex_subject_view`   — one subject's chapter → section tree.
- `codex_node_view`      — one content node: breadcrumb, full markdown
  content, children links, "Practice this topic" + "Start a Hunt" CTAs.

All pages extend `student/_shell.html` (dark System theme). The Codex
shares its content model with the in-chat Codex rail; both load the
same `ContentNode` rows.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from apps.core.decorators import role_required
from apps.service.models import ContentNode, Subject


def _tenant_content_qs(tenant):
    return ContentNode.objects.filter(tenant=tenant).select_related(
        'subject', 'parent', 'document',
    )


@login_required
@role_required(['student'])
def codex_list_view(request):
    """All subjects in the student's tenant + their chapter counts."""
    subjects = list(
        Subject.objects
        .filter(tenant=request.user.tenant, is_active=True)
        .annotate(
            chapter_count=Count(
                'contentnode',
                filter=Q(contentnode__node_type='chapter'),
            ),
            topic_count=Count(
                'contentnode',
                filter=Q(contentnode__node_type__in=['topic', 'section']),
            ),
        )
        .order_by('name')
    )

    # Enrich each with a preview of the first chapter (link target).
    for s in subjects:
        s.first_chapter = (
            ContentNode.objects
            .filter(tenant=request.user.tenant, subject=s, node_type='chapter')
            .order_by('position', 'id')
            .first()
        )

    profile = getattr(request.user, 'profile', None)
    return render(request, 'student/codex/list.html', {
        'user': request.user,
        'profile': profile,
        'subjects': subjects,
        'active_page': 'codex',
    })


@login_required
@role_required(['student'])
def codex_subject_view(request, subject_id):
    """Show all top-level (chapter) nodes for a subject, each with child section list."""
    subject = get_object_or_404(
        Subject, pk=subject_id, tenant=request.user.tenant, is_active=True,
    )
    chapters = list(
        _tenant_content_qs(request.user.tenant)
        .filter(subject=subject, node_type='chapter')
        .order_by('position', 'id')
    )
    chapter_ids = [c.id for c in chapters]
    # Pull sections per chapter in one query
    sections_by_chapter = {}
    for section in (
        _tenant_content_qs(request.user.tenant)
        .filter(parent_id__in=chapter_ids, node_type__in=['section', 'topic'])
        .order_by('position', 'id')
    ):
        sections_by_chapter.setdefault(section.parent_id, []).append(section)

    rows = [
        {
            'chapter': c,
            'sections': sections_by_chapter.get(c.id, []),
        }
        for c in chapters
    ]

    profile = getattr(request.user, 'profile', None)
    return render(request, 'student/codex/subject.html', {
        'user': request.user,
        'profile': profile,
        'subject': subject,
        'rows': rows,
        'chapter_count': len(chapters),
        'active_page': 'codex',
    })


@login_required
@role_required(['student'])
def codex_node_view(request, node_id):
    """Detail view for a single ContentNode: breadcrumb + content + children."""
    node = get_object_or_404(
        _tenant_content_qs(request.user.tenant), pk=node_id,
    )

    # Walk parents → breadcrumb (root first)
    breadcrumb = []
    cursor = node.parent
    while cursor is not None:
        breadcrumb.insert(0, cursor)
        cursor = cursor.parent

    children = list(
        _tenant_content_qs(request.user.tenant)
        .filter(parent=node)
        .order_by('position', 'id')
    )

    # Sibling nav — previous / next at same depth
    siblings = list(
        _tenant_content_qs(request.user.tenant)
        .filter(parent=node.parent, subject=node.subject)
        .order_by('position', 'id')
    )
    prev_sibling = None
    next_sibling = None
    for i, s in enumerate(siblings):
        if s.pk == node.pk:
            if i > 0:
                prev_sibling = siblings[i - 1]
            if i < len(siblings) - 1:
                next_sibling = siblings[i + 1]
            break

    profile = getattr(request.user, 'profile', None)
    return render(request, 'student/codex/node.html', {
        'user': request.user,
        'profile': profile,
        'node': node,
        'breadcrumb': breadcrumb,
        'children': children,
        'prev_sibling': prev_sibling,
        'next_sibling': next_sibling,
        'active_page': 'codex',
    })
