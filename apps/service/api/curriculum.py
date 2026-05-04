"""Read-only API for curriculum ContentNodes — used by the Codex right-rail.

The Codex panel on the student chat page calls this endpoint when a citation
chip is clicked. Citations come from `RetrievedChunk.node_id`, which is the
CharField `ContentNode.node_id` (e.g. "ch1.s1.t1"), not the integer PK. The
viewset therefore accepts either form in the URL slug: an all-digit slug is
tried as an integer PK first, anything else (or a miss) falls back to a
lookup by `node_id` CharField scoped to the caller's tenant.

The viewset is tenant-scoped and login-required. There is no create / update /
delete path — curriculum authoring happens elsewhere.
"""

from rest_framework import permissions, viewsets
from rest_framework.response import Response

from apps.service.models import ContentNode


class CurriculumNodeViewSet(viewsets.ViewSet):
    """Expose ContentNode data scoped to the authenticated user's tenant."""

    permission_classes = [permissions.IsAuthenticated]

    # Default DRF regex is `[^/.]+` which would reject dotted node_ids like
    # "ch1.s1.t1". Widen to anything except a slash so CharField node_ids
    # resolve too.
    lookup_value_regex = '[^/]+'

    def retrieve(self, request, pk=None):
        tenant = getattr(request.user, 'tenant', None)
        qs = ContentNode.objects.filter(tenant=tenant).select_related(
            'document', 'subject', 'parent',
        )

        # `pk` in the URL can be either the integer primary key or the
        # CharField `node_id` (what tutoring citations carry). Try integer
        # PK first when the slug is all digits, otherwise fall back to the
        # CharField lookup.
        node = None
        if pk is not None and str(pk).isdigit():
            node = qs.filter(pk=int(pk)).first()
        if node is None:
            node = qs.filter(node_id=str(pk)).first()
        if not node:
            return Response({'error': 'Not found'}, status=404)

        # Walk parents to build a breadcrumb from root down to the node's
        # immediate parent. `node` itself is not included — the consumer
        # renders it separately as the focused topic.
        breadcrumb = []
        cursor = node.parent
        while cursor is not None:
            breadcrumb.insert(0, {
                'id': cursor.id,
                'node_id': cursor.node_id,
                'title': cursor.title,
                'node_type': cursor.node_type,
            })
            cursor = cursor.parent

        # Sibling nodes sharing the same parent — a small "Related" list.
        related = list(
            ContentNode.objects
            .filter(parent=node.parent, tenant=tenant)
            .exclude(pk=node.pk)
            .values('id', 'node_id', 'title', 'node_type')[:5]
        ) if node.parent_id else []

        return Response({
            'id': node.id,
            'node_id': node.node_id,
            'title': node.title,
            'node_type': node.node_type,
            'content': node.content,
            'page_number': node.page_number,
            'subject': {
                'id': node.subject_id,
                'name': node.subject.name if node.subject else None,
            },
            'document': {
                'id': node.document_id,
                'title': node.document.title if node.document else None,
            },
            'breadcrumb': breadcrumb,
            'related': related,
        })
