"""
Tutoring REST endpoints.

ViewSet style chosen so future per-session resources (messages, ratings) can
hang off it as `@action`-decorated routes. Every method returns the project's
`APIResponse` envelope rather than a raw DRF `Response`, so the client-side
`APIClient` can stay uniform across all endpoints.
"""

import logging

from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.utils.response import APIResponse
from apps.service.models import TutoringSession
from apps.service.services.tutoring import TutorService

from .serializers import (
    ChatMessageSerializer,
    CreateMessageSerializer,
    TutoringSessionDetailSerializer,
    TutoringSessionSerializer,
)

logger = logging.getLogger(__name__)


class TutoringSessionViewSet(viewsets.ViewSet):
    """CRUD-ish endpoints for `TutoringSession` plus the `messages` action."""

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
        """`GET /api/v1/tutoring/sessions/` — current student's sessions."""
        if (err := self._student_only(request)):
            return err

        sessions = (
            TutoringSession.objects
            .filter(student=request.user, tenant=request.user.tenant)
            .select_related('subject')
            .prefetch_related('messages')
        )
        return APIResponse.success(
            data=TutoringSessionSerializer(sessions, many=True).data,
            message='Sessions fetched.',
        )

    # ------------------------------------------------------------------ create

    def create(self, request):
        """`POST /api/v1/tutoring/sessions/` — open a new session."""
        if (err := self._student_only(request)):
            return err

        title = (request.data.get('title') or '').strip()[:200]
        subject_id = request.data.get('subject') or None

        session = TutoringSession.objects.create(
            tenant=request.user.tenant,
            student=request.user,
            subject_id=subject_id,
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
        """`DELETE /api/v1/tutoring/sessions/<id>/` — soft archive (is_active=False)."""
        if (err := self._student_only(request)):
            return err

        session = self._own_session(request, pk)
        session.is_active = False
        session.save(update_fields=['is_active'])
        return APIResponse.success(message='Session archived.')

    # --------------------------------------------------------- nested messages

    @action(detail=True, methods=['get', 'post'], url_path='messages')
    def messages(self, request, pk=None):
        """`POST /api/v1/tutoring/sessions/<id>/messages/` — ask, get answer.

        `GET` returns the message history. `POST {content}` runs one Q&A round
        and returns both the persisted user turn and the assistant reply.
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

        # POST
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
        except Exception as exc:
            logger.exception('Tutor service error: %s', exc)
            return APIResponse.server_error('Tutor failed to answer. Please try again.')

        return APIResponse.success(
            data={
                'user_message': ChatMessageSerializer(answer.user_message).data,
                'assistant_message': ChatMessageSerializer(answer.assistant_message).data,
                'sources': [s.to_dict() for s in answer.sources],
                'model': answer.model,
            },
            message='Answer generated.',
            status=201,
        )
