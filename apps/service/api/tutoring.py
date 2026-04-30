"""
Tutoring REST endpoints.

ViewSet style chosen so future per-session resources (messages, ratings) can
hang off it as `@action`-decorated routes. Every non-streaming method returns
the project's `APIResponse` envelope; the streaming endpoint uses
`StreamingHttpResponse` with `text/event-stream` frames.

New-session creation no longer accepts a subject — the tutor picks it
dynamically per question via `QueryRouter`. The subject picker modal on the
student chat page has been removed accordingly.

Endpoints:

    GET    /api/v1/tutoring/sessions/                    list
    POST   /api/v1/tutoring/sessions/                    create (title only)
    GET    /api/v1/tutoring/sessions/<id>/               retrieve + messages
    DELETE /api/v1/tutoring/sessions/<id>/               archive
    GET    /api/v1/tutoring/sessions/<id>/messages/      history
    POST   /api/v1/tutoring/sessions/<id>/messages/      ask, blocking
    POST   /api/v1/tutoring/sessions/<id>/messages/stream/
                                                         ask, SSE streaming
"""

import json
import logging

from django.db.models.functions import Coalesce
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer, JSONRenderer

from apps.core.utils.response import APIResponse
from apps.service.models import TutoringSession
from apps.service.services.tutoring import TutorService, TutorUnavailable

from .serializers import (
    ChatMessageSerializer,
    CreateMessageSerializer,
    TutoringSessionDetailSerializer,
    TutoringSessionSerializer,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- renderers


class ServerSentEventRenderer(BaseRenderer):
    """Pass-through renderer so DRF's content negotiation accepts SSE.

    The browser sends `Accept: text/event-stream` on the streaming request.
    Without a renderer advertising that media type, DRF returns `406 Not
    Acceptable` before our view even runs. We don't use this renderer to
    format anything — the view returns a `StreamingHttpResponse` directly,
    which DRF leaves untouched. We keep `JSONRenderer` alongside so error
    envelopes (e.g. from the student-only guard) still serialise correctly.
    """

    media_type = 'text/event-stream'
    format = 'sse'
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # Only reached if a non-streaming path tries to use this renderer;
        # return the data untouched so no one blows up.
        if isinstance(data, (bytes, str)):
            return data
        return str(data)


# --------------------------------------------------------------------------- SSE helpers


def _sse_frame(event: dict) -> bytes:
    """Encode a router event as a single SSE frame.

    We carry an `event:` field so the client can pick the right handler
    without parsing the payload first. JSON-encoded data goes in `data:`.
    """
    etype = event.get('type', 'message')
    payload = event.get('data')
    body = json.dumps(payload, ensure_ascii=False, default=str)
    return f'event: {etype}\ndata: {body}\n\n'.encode('utf-8')


def _stream_events(event_iter):
    """Wrap a TutorService event generator as an SSE byte stream."""
    try:
        for evt in event_iter:
            yield _sse_frame(evt)
    except Exception as exc:  # defensive: never leak a bare exception to the socket
        logger.exception('SSE stream terminated: %s', exc)
        yield _sse_frame({'type': 'error', 'data': 'Stream failed.'})
    # Signal end-of-stream to the browser so EventSource-style clients close cleanly.
    yield b'event: close\ndata: {}\n\n'


def _streaming_response(event_iter) -> StreamingHttpResponse:
    response = StreamingHttpResponse(
        _stream_events(event_iter),
        content_type='text/event-stream; charset=utf-8',
    )
    # Tell nginx / Render / whatever reverse proxy to disable buffering,
    # otherwise the tokens pile up until the connection closes.
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# --------------------------------------------------------------------------- viewset


class TutoringSessionViewSet(viewsets.ViewSet):
    """CRUD-ish endpoints for `TutoringSession` + the `messages` action."""

    permission_classes = [IsAuthenticated]

    # ------------------------------------------------------------------ helpers

    def _student_only(self, request):
        """Reject non-students. Returns an APIResponse on failure, else None."""
        user = request.user
        if not getattr(user, 'is_student', False):
            return APIResponse.forbidden('Only students can use the AI tutor.')
        if not getattr(user, 'tenant_id', None):
            return APIResponse.error('Tenant context required.', status=400)
        return None

    def _own_session(self, request, pk):
        return get_object_or_404(
            TutoringSession,
            pk=pk,
            student=request.user,
            tenant=request.user.tenant,
        )

    # -------------------------------------------------------------------- list

    def list(self, request):
        """`GET /api/v1/tutoring/sessions/` — current student's sessions.

        Ordered by `COALESCE(last_message_at, created_at)` DESC so the row
        that was last-used appears first. Sorting by `-last_message_at`
        alone puts brand-new empty chats (NULL last_message_at) above older
        chats that just received a new message — which looked like "latest
        at the bottom" in the sidebar.
        """
        if (err := self._student_only(request)):
            return err

        sessions = (
            TutoringSession.objects
            .filter(student=request.user, tenant=request.user.tenant)
            .select_related('subject')
            .prefetch_related('messages')
            .annotate(latest_activity=Coalesce('last_message_at', 'created_at'))
            .order_by('-latest_activity')
        )
        return APIResponse.success(
            data=TutoringSessionSerializer(sessions, many=True).data,
            message='Sessions fetched.',
        )

    # ------------------------------------------------------------------ create

    def create(self, request):
        """`POST /api/v1/tutoring/sessions/` — open a new session.

        Body is optional: `{"title": "..."}` is accepted. Subject is no longer
        accepted here — the tutor infers it per question via the router.
        """
        if (err := self._student_only(request)):
            return err

        title = (request.data.get('title') or '').strip()[:200]
        session = TutoringSession.objects.create(
            tenant=request.user.tenant,
            student=request.user,
            title=title,
        )
        return APIResponse.success(
            data=TutoringSessionSerializer(session).data,
            message='Session created.',
            status=201,
        )

    # ---------------------------------------------------------------- retrieve

    def retrieve(self, request, pk=None):
        """`GET /api/v1/tutoring/sessions/<id>/` — session + nested messages."""
        if (err := self._student_only(request)):
            return err

        session = self._own_session(request, pk)
        return APIResponse.success(
            data=TutoringSessionDetailSerializer(session).data,
            message='Session fetched.',
        )

    # ---------------------------------------------------------------- destroy

    def destroy(self, request, pk=None):
        """`DELETE /api/v1/tutoring/sessions/<id>/` — soft archive."""
        if (err := self._student_only(request)):
            return err

        session = self._own_session(request, pk)
        session.is_active = False
        session.save(update_fields=['is_active'])
        return APIResponse.success(message='Session archived.')

    # --------------------------------------------------------- nested messages

    @action(detail=True, methods=['get', 'post'], url_path='messages')
    def messages(self, request, pk=None):
        """Blocking ask / list history.

        `GET` returns the message history. `POST {content}` runs one Q&A round
        and returns both the persisted user turn and the assistant reply plus
        the routing metadata and source list.
        """
        if (err := self._student_only(request)):
            return err

        session = self._own_session(request, pk)

        if request.method == 'GET':
            messages = session.messages.all()
            return APIResponse.success(
                data=ChatMessageSerializer(messages, many=True).data,
                message='Messages fetched.',
            )

        serializer = CreateMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.validation_error(serializer.errors)

        try:
            answer = TutorService().answer_question(
                session=session,
                student=request.user,
                query=serializer.validated_data['content'],
            )
        except PermissionError as exc:
            return APIResponse.forbidden(str(exc))
        except ValueError as exc:
            return APIResponse.error(str(exc), status=400)
        except TutorUnavailable as exc:
            # LLM misconfigured on the server: surface a clean 503 rather
            # than a demo / offline canned response.
            return APIResponse.error(str(exc), status=503)
        except Exception as exc:
            logger.exception('Tutor service error: %s', exc)
            return APIResponse.server_error('Tutor failed to answer. Please try again.')

        return APIResponse.success(
            data={
                'user_message': ChatMessageSerializer(answer.user_message).data,
                'assistant_message': ChatMessageSerializer(answer.assistant_message).data,
                'routing': answer.routing.to_dict(),
                'sources': [s.to_dict() for s in answer.sources],
                'model': answer.model,
                # Session payload so the client can refresh the sidebar row
                # and the chat header when the title changes (LLM-refined
                # after the first Q&A round).
                'session': {
                    'id': session.id,
                    'title': answer.session_title,
                    'title_changed': answer.title_changed,
                },
            },
            message='Answer generated.',
            status=201,
        )

    # ---------------------------------------------------------------- streaming

    @action(
        detail=True,
        methods=['post'],
        url_path='messages/stream',
        # Advertise `text/event-stream` so content negotiation succeeds when
        # the browser sends `Accept: text/event-stream`; keep JSON around so
        # the student-only / validation-error envelopes still render.
        renderer_classes=[ServerSentEventRenderer, JSONRenderer],
    )
    def messages_stream(self, request, pk=None):
        """`POST /api/v1/tutoring/sessions/<id>/messages/stream/` — SSE.

        Streams `text/event-stream` frames. Event types:

            event: user_message   → {id, role, content, ...}
            event: routing        → {subject_ids, subject_names, topics, intent, ...}
            event: sources        → [ {title, snippet, page_number, score, ...}, ... ]
            event: token          → "partial text"
            event: done           → {assistant_message, model, routing, sources}
            event: error          → "reason"
            event: close          → (final marker)

        Uses Django's `StreamingHttpResponse`. Validation errors for the body
        are returned as a one-shot error frame followed by close so the client
        path stays uniform.
        """
        if (err := self._student_only(request)):
            return err

        session = self._own_session(request, pk)
        serializer = CreateMessageSerializer(data=request.data)
        if not serializer.is_valid():
            def _bad_request_events():
                yield {'type': 'error', 'data': _first_error(serializer.errors)}
            return _streaming_response(_bad_request_events())

        event_iter = TutorService().stream_answer(
            session=session,
            student=request.user,
            query=serializer.validated_data['content'],
        )
        return _streaming_response(event_iter)


# --------------------------------------------------------------------------- helpers


def _first_error(errors) -> str:
    """Flatten a DRF error dict to a human-readable string."""
    if isinstance(errors, dict):
        for _, v in errors.items():
            if isinstance(v, (list, tuple)) and v:
                return str(v[0])
            return str(v)
    if isinstance(errors, (list, tuple)) and errors:
        return str(errors[0])
    return 'Invalid request.'
