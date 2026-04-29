"""
TutorService — orchestrates one Q&A round in a TutoringSession.

Flow:
    1. Persist the student's `ChatMessage`.
    2. Retrieve top-k curriculum chunks from the tenant's ChromaDB collection.
    3. If `OPENAI_API_KEY` is configured, call `LLMService.generate_with_context`;
       otherwise fall back to the offline `stub_answerer`.
    4. Persist the assistant's `ChatMessage` with the retrieved chunks attached.
    5. Touch the session's `last_message_at` and (if blank) auto-title from the
       first student question.

The service has no view-layer concerns. It is exercised by the DRF ViewSet
in `apps/service/api/tutoring.py` and is also directly testable from unit
tests, which is how we verify behaviour without a paid LLM.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.service.models import ChatMessage, TutoringSession

from . import stub_answerer
from .prompts import build_system_prompt
from .retriever import CurriculumRetriever, RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
DEFAULT_TITLE_LENGTH = 80


@dataclass
class TutorAnswer:
    """Return shape of `TutorService.answer_question`."""
    user_message: ChatMessage
    assistant_message: ChatMessage
    sources: List[RetrievedChunk]
    model: str

    def to_dict(self) -> dict:
        return {
            'user_message_id': self.user_message.id,
            'assistant_message_id': self.assistant_message.id,
            'answer': self.assistant_message.content,
            'model': self.model,
            'sources': [s.to_dict() for s in self.sources],
        }


class TutorService:
    """Run one Q&A round against curriculum-grounded RAG."""

    def __init__(
        self,
        retriever: Optional[CurriculumRetriever] = None,
        llm_service=None,
    ):
        self._retriever = retriever or CurriculumRetriever()
        self._llm_service = llm_service  # lazy-init when needed

    @property
    def llm_service(self):
        if self._llm_service is None:
            from clients.llm import LLMService
            self._llm_service = LLMService()
        return self._llm_service

    @transaction.atomic
    def answer_question(
        self,
        session: TutoringSession,
        student: User,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> TutorAnswer:
        """Run one full RAG round and persist both messages."""
        if session.student_id != student.id:
            raise PermissionError('Session does not belong to this student.')
        if session.tenant_id != student.tenant_id:
            raise PermissionError('Session belongs to a different tenant.')

        query = (query or '').strip()
        if not query:
            raise ValueError('Query must not be empty.')

        user_message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.STUDENT,
            content=query,
            retrieved_chunks=[],
            model='',
        )

        sources = self._retriever.retrieve(
            tenant=session.tenant,
            query=query,
            top_k=top_k,
            subject_id=session.subject_id,
        )

        answer_text, model_name = self._build_answer(query, sources, student)

        assistant_message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=answer_text,
            retrieved_chunks=[s.to_dict() for s in sources],
            model=model_name,
        )

        # Touch session metadata: last_message_at + auto-title.
        update_fields = ['last_message_at']
        session.last_message_at = timezone.now()
        if not session.title:
            session.title = query[:DEFAULT_TITLE_LENGTH]
            update_fields.append('title')
        session.save(update_fields=update_fields)

        return TutorAnswer(
            user_message=user_message,
            assistant_message=assistant_message,
            sources=sources,
            model=model_name,
        )

    def _build_answer(
        self,
        query: str,
        sources: List[RetrievedChunk],
        student: User,
    ) -> tuple[str, str]:
        """Pick stub vs real LLM, return (answer_text, model_name)."""
        api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
        if not api_key:
            return stub_answerer.answer(query, sources), stub_answerer.STUB_MODEL_NAME

        if not sources:
            # Don't burn LLM tokens when there's no grounding context.
            return stub_answerer.answer(query, sources), stub_answerer.STUB_MODEL_NAME

        try:
            grade_level = getattr(student, 'grade_level', None)
            result = self.llm_service.generate_with_context(
                query=query,
                context_chunks=[s.snippet for s in sources],
                system_prompt=build_system_prompt(grade_level),
            )
            return result['answer'], result.get('model', '')
        except Exception as exc:
            logger.exception('LLM generation failed; falling back to stub: %s', exc)
            return stub_answerer.answer(query, sources), stub_answerer.STUB_MODEL_NAME
