"""Student chat (AI tutor) page.

The view itself is intentionally thin: it renders the chat shell and lets the
JavaScript layer hydrate the session list, messages, and answer flow against
the `/api/v1/tutoring/sessions/...` endpoints via `APIClient`.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.decorators import role_required
from apps.service.models import Subject, TutoringSession


@login_required
@role_required(['student'])
def chat_view(request, session_id: int | None = None):
    """Render the chat page for the logged-in student."""
    sessions = (
        TutoringSession.objects
        .filter(student=request.user, tenant=request.tenant)
        .select_related('subject')
        .order_by('-last_message_at', '-created_at')
    )
    subjects = Subject.objects.filter(tenant=request.tenant, is_active=True).order_by('name')

    active_session = None
    if session_id is not None:
        active_session = sessions.filter(pk=session_id).first()

    return render(request, 'student/chat.html', {
        'user': request.user,
        'sessions': sessions,
        'subjects': subjects,
        'active_session': active_session,
    })
