"""
TutorService — orchestrates one Q&A round in a TutoringSession.

Pipeline:

    student question
        │
        ▼
    1. persist user ChatMessage
        │
        ▼
    2. build student catalog  (subjects + chapters for their grade, cached)
        │
        ▼
    3. router.route(query, catalog, history)    ──► 1 LLM call (JSON mode)
        │                                            returns {subject_ids,
        │                                                     topic_titles,
        │                                                     refined_query,
        │                                                     intent,
        │                                                     needs_retrieval}
        ▼
    4. retriever.retrieve(refined_query, subject_ids=…)   (pgvector, filtered)
        │
        ▼
    5. answer generation
        - blocking:  LLMService.generate_with_context(stream=False)
        - streaming: LLMService.generate_with_context(stream=True)
                     + token callback → SSE
        │
        ▼
    6. persist assistant ChatMessage (sources + routing metadata)

Two entry points:

  * `answer_question(...)`      → runs the whole flow synchronously and
                                  returns one `TutorAnswer` bundle. Used by
                                  the non-streaming API path and by tests.
  * `stream_answer(...)`        → generator that yields event dicts for SSE
                                  (`user_message`, `routing`, `sources`,
                                  `token`, `done`, `error`). Persists both
                                  turns, auto-titles the session, etc.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.service.models import ChatMessage, TutoringSession

from .catalog import get_student_catalog
from .prompts import (
    TITLE_SYSTEM_PROMPT,
    TutorUnavailable,
    UNAVAILABLE_MESSAGE,
    build_no_context_system_prompt,
    build_title_prompt,
    build_tutor_system_prompt,
    build_upstream_error_message,
    short_circuit_system_prompt,
)
from .retriever import CurriculumRetriever, RetrievedChunk
from .router import QueryRouter, Routing

logger = logging.getLogger(__name__)


DEFAULT_TOP_K = 5
DEFAULT_TITLE_LENGTH = 80
MAX_TITLE_LENGTH = 80

# How many prior ChatMessages to include as conversation history (both roles).
HISTORY_WINDOW = 8


# --------------------------------------------------------------------------- result types


@dataclass
class TutorAnswer:
    """Return shape of `TutorService.answer_question`."""
    user_message: ChatMessage
    assistant_message: ChatMessage
    sources: List[RetrievedChunk]
    routing: Routing
    model: str
    session_title: str = ''
    title_changed: bool = False

    def to_dict(self) -> dict:
        return {
            'user_message_id': self.user_message.id,
            'assistant_message_id': self.assistant_message.id,
            'answer': self.assistant_message.content,
            'model': self.model,
            'routing': self.routing.to_dict(),
            'sources': [s.to_dict() for s in self.sources],
            'session': {
                'title': self.session_title,
                'title_changed': self.title_changed,
            },
        }


# --------------------------------------------------------------------------- service


class TutorService:
    """Run one Q&A round against curriculum-grounded RAG."""

    def __init__(
        self,
        retriever: Optional[CurriculumRetriever] = None,
        router: Optional[QueryRouter] = None,
        llm_service=None,
    ):
        self._retriever = retriever or CurriculumRetriever()
        self._router = router or QueryRouter(llm_service=llm_service)
        self._llm_service = llm_service  # lazy

    # ---------------------------------------------------------------- lazy deps

    @property
    def llm_service(self):
        if self._llm_service is None:
            from clients.llm import LLMService
            self._llm_service = LLMService()
        return self._llm_service

    # ---------------------------------------------------------------- public API (blocking)

    def answer_question(
        self,
        session: TutoringSession,
        student: User,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> TutorAnswer:
        """Full synchronous pipeline. Both messages persisted; no streaming."""
        self._assert_session_ownership(session, student)
        query = self._assert_non_empty(query)
        self._ensure_llm_configured()

        user_message = self._persist_user_message(session, query)

        history = self._build_history(session, exclude_id=user_message.id)
        catalog = get_student_catalog(student)
        routing = self._router.route(
            query=query,
            catalog=catalog,
            grade_level=getattr(student, 'grade_level', None),
            history=history,
        )

        sources = self._retrieve(
            session=session,
            routing=routing,
            top_k=top_k,
        )

        answer_text, model_name = self._generate_answer(
            query=query,
            routing=routing,
            sources=sources,
            student=student,
            history=history,
        )

        assistant_message = self._persist_assistant_message(
            session=session,
            text=answer_text,
            sources=sources,
            model=model_name,
            routing=routing,
        )
        self._touch_session(session, user_message)

        # After the first full Q&A round, refine the sidebar title with the
        # LLM so it reads like "Quadratic Formula Explained" instead of the
        # raw truncated question. Subsequent rounds leave the title alone.
        title_changed = self._maybe_refine_title(
            session=session,
            query=query,
            answer_text=answer_text,
            routing=routing,
        )

        return TutorAnswer(
            user_message=user_message,
            assistant_message=assistant_message,
            sources=sources,
            routing=routing,
            model=model_name,
            session_title=session.title,
            title_changed=title_changed,
        )

    # ---------------------------------------------------------------- public API (streaming)

    def stream_answer(
        self,
        session: TutoringSession,
        student: User,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> Iterator[Dict]:
        """Yield SSE-friendly event dicts while running the pipeline.

        Event shape:
            {'type': 'user_message', 'data': {...}}
            {'type': 'routing',      'data': {...}}
            {'type': 'sources',      'data': [...]}
            {'type': 'token',        'data': 'partial text'}
            {'type': 'done',         'data': {...}}
            {'type': 'error',        'data': 'reason'}

        The caller is responsible for turning these into text/event-stream
        frames (see apps/service/api/tutoring.py).
        """
        try:
            self._assert_session_ownership(session, student)
            query = self._assert_non_empty(query)
            self._ensure_llm_configured()
        except (PermissionError, ValueError) as exc:
            yield {'type': 'error', 'data': str(exc)}
            return
        except TutorUnavailable as exc:
            yield {'type': 'error', 'data': str(exc)}
            return

        # Persist the user turn up-front so that a client disconnect mid-stream
        # still leaves a visible question in the session history.
        user_message = self._persist_user_message(session, query)
        yield {
            'type': 'user_message',
            'data': _serialize_message(user_message),
        }

        history = self._build_history(session, exclude_id=user_message.id)
        catalog = get_student_catalog(student)
        routing = self._router.route(
            query=query,
            catalog=catalog,
            grade_level=getattr(student, 'grade_level', None),
            history=history,
        )
        yield {'type': 'routing', 'data': routing.to_dict()}

        sources = self._retrieve(session=session, routing=routing, top_k=top_k)
        yield {'type': 'sources', 'data': [s.to_dict() for s in sources]}

        collected: List[str] = []
        model_name = self.llm_service.model
        upstream_error: Optional[BaseException] = None
        try:
            token_stream = self._iter_answer_tokens(
                query=query,
                routing=routing,
                sources=sources,
                student=student,
                history=history,
            )
            for piece, current_model in token_stream:
                model_name = current_model
                collected.append(piece)
                yield {'type': 'token', 'data': piece}
        except Exception as exc:
            # Runtime failure calling the LLM (bad URL, 401, timeout, …).
            # Full traceback to the log for the admin; a concrete but
            # sanitised summary to the student so they can report it.
            upstream_error = exc
            logger.exception(
                'Tutor LLM call failed (base_url=%s, model=%s): %s',
                getattr(self.llm_service, '_base_url', '?'),
                getattr(self.llm_service, 'model', '?'),
                exc,
            )
            yield {'type': 'error', 'data': build_upstream_error_message(exc)}

        answer_text = ''.join(collected).strip()
        if not answer_text:
            # Nothing came back. If we captured an upstream exception,
            # surface its type + message. Otherwise fall back to the
            # generic "unavailable" wording (rare — model returned 0 tokens).
            answer_text = (
                build_upstream_error_message(upstream_error)
                if upstream_error is not None
                else UNAVAILABLE_MESSAGE
            )
            yield {'type': 'token', 'data': answer_text}

        assistant_message = self._persist_assistant_message(
            session=session,
            text=answer_text,
            sources=sources,
            model=model_name,
            routing=routing,
        )
        self._touch_session(session, user_message)

        # LLM-refined sidebar title after the first Q&A round.
        title_changed = self._maybe_refine_title(
            session=session,
            query=query,
            answer_text=answer_text,
            routing=routing,
        )
        if title_changed:
            yield {
                'type': 'title',
                'data': {
                    'session_id': session.id,
                    'title': session.title,
                },
            }

        yield {
            'type': 'done',
            'data': {
                'assistant_message': _serialize_message(assistant_message),
                'model': model_name,
                'routing': routing.to_dict(),
                'sources': [s.to_dict() for s in sources],
                'session': {
                    'id': session.id,
                    'title': session.title,
                    'title_changed': title_changed,
                },
            },
        }

    # ---------------------------------------------------------------- internals: validation

    @staticmethod
    def _assert_session_ownership(session: TutoringSession, student: User) -> None:
        if session.student_id != student.id:
            raise PermissionError('Session does not belong to this student.')
        if session.tenant_id != student.tenant_id:
            raise PermissionError('Session belongs to a different tenant.')

    @staticmethod
    def _assert_non_empty(query: str) -> str:
        q = (query or '').strip()
        if not q:
            raise ValueError('Query must not be empty.')
        return q

    # ---------------------------------------------------------------- internals: persistence

    @staticmethod
    def _persist_user_message(session: TutoringSession, query: str) -> ChatMessage:
        return ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.STUDENT,
            content=query,
            retrieved_chunks=[],
            model='',
            metadata={},
        )

    @staticmethod
    def _persist_assistant_message(
        *,
        session: TutoringSession,
        text: str,
        sources: List[RetrievedChunk],
        model: str,
        routing: Routing,
    ) -> ChatMessage:
        return ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=text,
            retrieved_chunks=[s.to_dict() for s in sources],
            model=model,
            metadata={'routing': routing.to_dict()},
        )

    @staticmethod
    @transaction.atomic
    def _touch_session(session: TutoringSession, user_message: ChatMessage) -> None:
        """Update `last_message_at` and auto-title from the first question."""
        update_fields = ['last_message_at']
        session.last_message_at = timezone.now()
        if not session.title:
            session.title = user_message.content[:DEFAULT_TITLE_LENGTH]
            update_fields.append('title')
        session.save(update_fields=update_fields)

    # ---------------------------------------------------------------- internals: title

    def _maybe_refine_title(
        self,
        *,
        session: TutoringSession,
        query: str,
        answer_text: str,
        routing: Optional[Routing] = None,
    ) -> bool:
        """Generate a nicer sidebar title after the first Q&A round.

        The first question's first 80 characters are used as a placeholder
        title by `_touch_session`. Here we replace that placeholder with a
        concise LLM-crafted title ("Quadratic Formula Explained", etc.) so
        the sidebar reads well. Subsequent rounds leave the title alone
        because the student may have renamed the session in the UI.

        Skipped when the first turn was chitchat/meta — a session titled
        "Hi Hello" is less useful than the raw greeting anyway, and the
        student will usually follow up with a real question.

        Returns True iff the title was changed.
        """
        # Only refine on the very first round — 1 user turn + 1 assistant turn.
        if session.messages.count() != 2:
            return False
        if not answer_text or not answer_text.strip():
            return False
        if routing is not None and routing.intent in ('chitchat', 'meta'):
            return False

        try:
            raw = self.llm_service.generate(
                prompt=build_title_prompt(query, answer_text),
                system=TITLE_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=24,
            )
        except Exception as exc:
            logger.warning('title refinement failed for session=%s: %s', session.id, exc)
            return False

        cleaned = _clean_title(raw)
        if not cleaned or cleaned == session.title:
            return False

        session.title = cleaned
        session.save(update_fields=['title'])
        return True

    # ---------------------------------------------------------------- internals: history

    @staticmethod
    def _build_history(
        session: TutoringSession,
        *,
        exclude_id: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Most recent turns in OpenAI chat format (oldest → newest)."""
        qs = session.messages.all()
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        recent = list(qs.order_by('-created_at')[:HISTORY_WINDOW])[::-1]
        role_map = {
            ChatMessage.Role.STUDENT: 'user',
            ChatMessage.Role.ASSISTANT: 'assistant',
        }
        return [
            {'role': role_map.get(m.role, 'user'), 'content': m.content}
            for m in recent
        ]

    # ---------------------------------------------------------------- internals: retrieval

    def _retrieve(
        self,
        *,
        session: TutoringSession,
        routing: Routing,
        top_k: int,
    ) -> List[RetrievedChunk]:
        if not routing.needs_retrieval:
            return []
        subject_ids = routing.subject_ids or None
        return self._retriever.retrieve(
            tenant=session.tenant,
            query=routing.refined_query,
            top_k=top_k,
            subject_ids=subject_ids,
            topic_titles=routing.topic_titles or None,
        )

    # ---------------------------------------------------------------- internals: generation

    def _generate_answer(
        self,
        *,
        query: str,
        routing: Routing,
        sources: List[RetrievedChunk],
        student: User,
        history: List[Dict[str, str]],
    ) -> tuple[str, str]:
        """Pick the right LLM branch (chitchat / RAG / no-context) and return text + model.

        Every branch goes through the real LLM — there is no demo / offline
        fallback content. If the LLM call itself raises, we re-raise so the
        API layer can surface a proper error to the student instead of a
        canned "offline" message.
        """
        # Chitchat / meta: small talk without burning retrieval tokens.
        if not routing.needs_retrieval:
            return self._generate_chitchat(query, routing, history), self.llm_service.model

        if sources:
            # Grounded RAG answer — the normal path.
            system_prompt = build_tutor_system_prompt(
                grade_level=getattr(student, 'grade_level', None),
                subject_names=routing.subject_names,
                topic_titles=routing.topic_titles,
                intent=routing.intent,
            )
            result = self.llm_service.generate_with_context(
                query=query,
                context_chunks=[s.snippet for s in sources],
                system_prompt=system_prompt,
                history=history or None,
            )
            return result['answer'], result.get('model', self.llm_service.model)

        # Retrieval returned nothing — still answer with the LLM, but tell
        # it to rely on general knowledge and skip citations.
        system_prompt = build_no_context_system_prompt(
            grade_level=getattr(student, 'grade_level', None),
            subject_names=routing.subject_names,
            intent=routing.intent,
        )
        answer = self.llm_service.generate(
            prompt=query,
            system=system_prompt,
            temperature=0.5,
            history=history or None,
        )
        return answer, self.llm_service.model

    def _iter_answer_tokens(
        self,
        *,
        query: str,
        routing: Routing,
        sources: List[RetrievedChunk],
        student: User,
        history: List[Dict[str, str]],
    ) -> Iterator[tuple[str, str]]:
        """Yield `(piece, model_name)` tuples for SSE streaming.

        Three branches — all LLM-backed (no demo text):
          * chitchat / meta  → short chit-chat stream, no retrieval
          * RAG              → streamed answer with numbered context + history
          * no retrieval hits → streamed answer with the no-context prompt
        """
        if not routing.needs_retrieval:
            system = short_circuit_system_prompt(routing.intent)
            for piece in self.llm_service.generate_stream(
                prompt=query,
                system=system,
                temperature=0.4,
                max_tokens=180,
                history=history or None,
            ):
                yield piece, self.llm_service.model
            return

        if sources:
            system_prompt = build_tutor_system_prompt(
                grade_level=getattr(student, 'grade_level', None),
                subject_names=routing.subject_names,
                topic_titles=routing.topic_titles,
                intent=routing.intent,
            )
            stream = self.llm_service.generate_with_context(
                query=query,
                context_chunks=[s.snippet for s in sources],
                system_prompt=system_prompt,
                history=history or None,
                stream=True,
            )
            for piece in stream:  # type: ignore[union-attr]
                yield piece, self.llm_service.model
            return

        # No matching curriculum chunks — still stream from the LLM but with
        # the no-context system prompt (no citations, general knowledge).
        system_prompt = build_no_context_system_prompt(
            grade_level=getattr(student, 'grade_level', None),
            subject_names=routing.subject_names,
            intent=routing.intent,
        )
        for piece in self.llm_service.generate_stream(
            prompt=query,
            system=system_prompt,
            temperature=0.5,
            history=history or None,
        ):
            yield piece, self.llm_service.model

    def _generate_chitchat(
        self,
        query: str,
        routing: Routing,
        history: List[Dict[str, str]],
    ) -> str:
        system = short_circuit_system_prompt(routing.intent)
        return self.llm_service.generate(
            prompt=query,
            system=system,
            temperature=0.4,
            max_tokens=180,
            history=history or None,
        )

    # ---------------------------------------------------------------- internals: config

    @staticmethod
    def _is_llm_configured() -> bool:
        """True when `OPENAI_API_KEY` has a non-empty, non-whitespace value.

        Checked against `django.conf.settings` which is populated from:
          * `.env` at import time
          * active `AppSetting` rows at startup (`CoreConfig.ready`)
          * live `AppSetting` rows at request time (`_refresh_runtime_config`)
        """
        value = getattr(settings, 'OPENAI_API_KEY', '') or ''
        return bool(value.strip())

    def _refresh_runtime_config(self) -> None:
        """Pull the latest admin-edited `AppSetting` rows into `settings`.

        Previously this only ran once per process in `CoreConfig.ready()`,
        which meant any change made in `/admin/core/appsetting/` required a
        server restart before the tutor would pick it up. Running it per
        request makes admin edits live — at the cost of one tiny SELECT
        query. Any cached LLM clients are invalidated so they re-read the
        fresh `settings` on their next access.
        """
        try:
            from apps.core.models.app_setting import AppSetting
            AppSetting.apply_to_settings()
        except Exception as exc:
            # Non-fatal: if the AppSetting table isn't reachable we still
            # fall back to whatever `settings` already holds from .env.
            logger.debug('AppSetting refresh skipped (non-fatal): %s', exc)
            return

        # Drop cached LLM clients so the next access re-reads fresh settings.
        self._llm_service = None
        router_attr = getattr(self._router, '_llm', object())
        if router_attr is None or hasattr(self._router, '_llm'):
            try:
                self._router._llm = None
            except Exception:
                pass

    def _ensure_llm_configured(self) -> None:
        """Raise `TutorUnavailable` if the LLM is not usable.

        Re-applies admin-editable `AppSetting` rows first so an admin who
        just updated the key / base URL / model doesn't need to restart
        the server. Logs a pointed hint on rejection so the admin can
        check the exact cause in the server log.
        """
        self._refresh_runtime_config()
        if self._is_llm_configured():
            return

        # Diagnostic: look up what the admin actually has saved so the
        # operator can see the concrete problem in the server log.
        logger.error(
            'Tutor request rejected: OPENAI_API_KEY is empty in settings. '
            '%s Check /admin/core/appsetting/ → key must be exactly '
            '"OPENAI_API_KEY", is_active=True, and the value non-empty.',
            _describe_llm_appsetting(),
        )
        raise TutorUnavailable(UNAVAILABLE_MESSAGE)


# --------------------------------------------------------------------------- helpers


def _serialize_message(msg: ChatMessage) -> dict:
    """Flat dict matching `ChatMessageSerializer` for SSE events."""
    return {
        'id': msg.id,
        'role': msg.role,
        'content': msg.content,
        'retrieved_chunks': msg.retrieved_chunks,
        'model': msg.model,
        'metadata': msg.metadata,
        'created_at': msg.created_at.isoformat() if msg.created_at else None,
    }


def _describe_llm_appsetting() -> str:
    """One-line human-readable state of the `OPENAI_API_KEY` AppSetting row.

    Used only in the server log when we reject a request; helps the admin
    understand whether the row is missing, inactive, or blank without them
    having to click into Django admin.
    """
    try:
        from apps.core.models.app_setting import AppSetting
    except Exception:
        return 'AppSetting table unreachable;'

    # Case-insensitive match — typos like lowercase are the #1 cause.
    rows = list(AppSetting.objects.filter(key__iexact='OPENAI_API_KEY'))
    if not rows:
        return 'No AppSetting row with key "OPENAI_API_KEY" exists.'

    bits = []
    for row in rows:
        key_match = '✓' if row.key == 'OPENAI_API_KEY' else f'✗ (got "{row.key}")'
        active = 'active' if row.is_active else 'INACTIVE'
        val = (row.value or '').strip()
        populated = f'value={len(val)} chars' if val else 'value=EMPTY'
        bits.append(f'[key={key_match}, {active}, {populated}]')
    return 'AppSetting row(s): ' + ' '.join(bits) + '.'


_TITLE_STRIP_CHARS = ''.join(['"', "'", '`', '“', '”', '‘', '’', '.', '!', '?', ':', ';', ' '])


def _clean_title(raw: str) -> str:
    """Trim the LLM's title output and enforce our length cap.

    Strips quotes / trailing punctuation / whitespace, collapses internal
    whitespace, drops newlines, truncates to `MAX_TITLE_LENGTH`. Returns ''
    if nothing useful is left.
    """
    if not raw:
        return ''
    # First non-empty line only — defends against chatty responses.
    line = next((ln for ln in raw.splitlines() if ln.strip()), '').strip()
    # Strip matched surrounding quotes repeatedly in case of nested.
    prev = None
    while prev != line:
        prev = line
        line = line.strip(_TITLE_STRIP_CHARS)
    # Collapse internal whitespace.
    line = ' '.join(line.split())
    return line[:MAX_TITLE_LENGTH]
