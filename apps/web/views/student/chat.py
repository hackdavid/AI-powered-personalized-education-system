"""Student chat (AI tutor) page.

The view itself is intentionally thin: it renders the chat shell and lets the
JavaScript layer hydrate the session list, messages, and answer flow against
the `/api/v1/tutoring/sessions/...` endpoints via `APIClient`.

Subject selection happens dynamically now — the tutor's `QueryRouter` infers
the right subject per question. The view no longer passes a `subjects`
context or renders a "new session" subject picker modal.
"""

from django.contrib.auth.decorators import login_required
from django.db.models.functions import Coalesce
from django.shortcuts import render

from apps.core.decorators import role_required
from apps.service.models import TutoringSession


@login_required
@role_required(['student'])
def chat_view(request, session_id: int | None = None):
    """Render the chat page for the logged-in student.

    Sidebar ordering uses `COALESCE(last_message_at, created_at)` DESC so
    a session's position follows its actual activity regardless of whether
    it has messages yet. Sorting by `-last_message_at` alone puts rows
    with `NULL last_message_at` (brand-new empty chats) ahead of older
    sessions that just received a new message — which looks like "latest
    at the bottom" to the student.
    """
    sessions = (
        TutoringSession.objects
        .filter(student=request.user, tenant=request.tenant)
        .select_related('subject')
        .annotate(latest_activity=Coalesce('last_message_at', 'created_at'))
        .order_by('-latest_activity')
    )

    active_session = None
    if session_id is not None:
        active_session = sessions.filter(pk=session_id).first()

    return render(request, 'student/chat.html', {
        'user': request.user,
        'sessions': sessions,
        'active_session': active_session,
    })
