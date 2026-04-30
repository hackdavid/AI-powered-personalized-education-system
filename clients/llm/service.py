"""
OpenAI-compatible LLM client.

Single client used across the whole project (tutor router, tutor answerer,
question generator, ingestion pipeline). Talks to any OpenAI-compatible HTTP
endpoint — official OpenAI, Azure OpenAI, Ollama, vLLM, Together, etc. — via
a configurable `base_url`.

Configuration precedence (lowest → highest):

  1. .env / os.environ          (read by config/settings.py at import time)
  2. AppSetting DB rows         (applied by CoreConfig.ready() at startup)
  3. Constructor kwargs         (when code explicitly builds a custom client)
  4. Per-call kwargs            (`model=`, `temperature=`, `response_format=`)

The project uses a single `LLMService()` instance (one model name for every
call site). Per-call kwargs are reserved for small deviations — for example
the router passes `temperature=0` + `response_format={"type":"json_object"}`
while still hitting the same underlying model.

Public surface:

  * `generate(prompt, system='', ...)`          → text
  * `generate_stream(prompt, system='', ...)`   → iterator of text chunks
  * `generate_structured(prompt, system='', ...)` → parsed dict (JSON mode,
    with a regex-extract fallback for endpoints that don't honour
    response_format)
  * `generate_with_context(query, chunks, ...)` → RAG helper. Pass
    `stream=True` to get an iterator of chunks instead of a dict.

Legacy attributes `.client` and `._model_name` are kept because the
ingestion pipeline touches them directly.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- helpers


_JSON_BLOCK_RE = re.compile(r'\{.*\}', re.DOTALL)


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort: pull the first `{...}` block out of an LLM response."""
    if not text:
        return None
    # Strip ```json fences if present
    fenced = re.search(r'```(?:json)?\s*(.*?)```', text, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else text
    match = _JSON_BLOCK_RE.search(candidate)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- main


class LLMService:
    """OpenAI-compatible LLM client with streaming + JSON-mode helpers."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        *,
        timeout: Optional[float] = 60.0,
        max_retries: int = 2,
        extra_headers: Optional[Dict[str, str]] = None,
        # Back-compat alias
        model_name: Optional[str] = None,
    ):
        # Strip whitespace on every string setting — copy-paste from the
        # Django admin UI frequently carries trailing spaces / newlines,
        # which would otherwise sail through and 401 at request time.
        def _clean(val, default=''):
            return (val if val is not None else default).strip()

        self._base_url = _clean(
            base_url or getattr(settings, 'OPENAI_BASE_URL', 'https://api.openai.com/v1'),
            'https://api.openai.com/v1',
        )
        self._api_key = _clean(api_key or getattr(settings, 'OPENAI_API_KEY', ''))
        self._model = _clean(
            model or model_name or getattr(settings, 'OPENAI_MODEL_NAME', 'gpt-4o-mini'),
            'gpt-4o-mini',
        )
        self._timeout = timeout
        self._max_retries = max_retries
        self._extra_headers = extra_headers or {}
        self._client = None

    # ---------------------------------------------------------------- client

    @property
    def model(self) -> str:
        """Default model name used for every call that doesn't override."""
        return self._model

    # Legacy alias kept because ingestion code reads `self.llm._model_name`.
    @property
    def _model_name(self) -> str:
        return self._model

    @property
    def client(self):
        """Lazy OpenAI client; lives for the lifetime of this LLMService."""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self._base_url,
                api_key=self._api_key or 'sk-missing',  # SDK requires non-empty
                timeout=self._timeout,
                max_retries=self._max_retries,
                default_headers=self._extra_headers or None,
            )
            logger.debug(
                'LLM client initialised: base_url=%s model=%s',
                self._base_url, self._model,
            )
        return self._client

    @property
    def is_configured(self) -> bool:
        """True when an API key is present. Callers gate behaviour on this."""
        return bool(self._api_key)

    # ---------------------------------------------------------------- internals

    def _build_messages(
        self,
        prompt: str,
        system: str = '',
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({'role': 'system', 'content': system})
        if history:
            messages.extend(history)
        messages.append({'role': 'user', 'content': prompt})
        return messages

    def _create(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        stream: bool = False,
        extra: Optional[dict] = None,
    ):
        """Thin wrapper over `client.chat.completions.create` with pruning."""
        kwargs: Dict[str, Any] = {
            'model': model or self._model,
            'messages': messages,
            'temperature': temperature,
            'stream': stream,
        }
        if max_tokens is not None:
            kwargs['max_tokens'] = max_tokens
        if response_format is not None:
            kwargs['response_format'] = response_format
        if extra:
            kwargs.update(extra)
        return self.client.chat.completions.create(**kwargs)

    # ---------------------------------------------------------------- text

    def generate(
        self,
        prompt: str,
        system: str = '',
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        history: Optional[List[Dict[str, str]]] = None,
        extra: Optional[dict] = None,
    ) -> str:
        """Blocking text completion. Returns the model's reply as a string."""
        messages = self._build_messages(prompt, system=system, history=history)
        response = self._create(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            stream=False,
            extra=extra,
        )
        return response.choices[0].message.content or ''

    # ---------------------------------------------------------------- streaming

    def generate_stream(
        self,
        prompt: str,
        system: str = '',
        *,
        model: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None,
        extra: Optional[dict] = None,
    ) -> Iterator[str]:
        """Yield text deltas as they stream in. Silent on empty chunks."""
        messages = self._build_messages(prompt, system=system, history=history)
        stream = self._create(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra=extra,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta
            except (AttributeError, IndexError):
                continue
            piece = getattr(delta, 'content', None)
            if piece:
                yield piece

    # ---------------------------------------------------------------- JSON mode

    def generate_structured(
        self,
        prompt: str,
        system: str = '',
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None,
        extra: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Ask the model for JSON and parse it.

        Tries native `response_format={"type":"json_object"}` first. If the
        endpoint rejects that (some OpenAI-compatible servers don't support
        it yet) we retry without the flag and recover the JSON with a
        regex-extract fallback. On failure returns `{}` rather than raising,
        so callers can fall back to heuristic routing.
        """
        messages = self._build_messages(prompt, system=system, history=history)

        attempts: List[Optional[dict]] = [{'type': 'json_object'}, None]
        raw: str = ''
        for rf in attempts:
            try:
                response = self._create(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=rf,
                    stream=False,
                    extra=extra,
                )
                raw = response.choices[0].message.content or ''
            except Exception as exc:
                # Try the next attempt (usually: drop response_format).
                logger.debug('structured generate attempt failed (rf=%s): %s', rf, exc)
                continue

            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                extracted = _extract_json(raw)
                if extracted is not None:
                    return extracted
        logger.warning('generate_structured: could not parse JSON; raw=%r', raw[:400])
        return {}

    # ---------------------------------------------------------------- RAG

    def generate_with_context(
        self,
        query: str,
        context_chunks: List[str],
        system_prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None,
        stream: bool = False,
    ) -> Union[Dict[str, Any], Iterator[str]]:
        """RAG helper: numbered context + query → cited answer.

        * `stream=False` (default) → returns a dict with `answer`, `sources`,
          `model`, `timestamp`. Safe to persist.
        * `stream=True` → returns an iterator of text deltas. Caller is
          responsible for accumulating and persisting the final string.
        """
        numbered_context = '\n\n'.join(
            f'[{i + 1}] {chunk}' for i, chunk in enumerate(context_chunks)
        )
        prompt = (
            'Context from curriculum materials (cite with bracketed numbers):\n'
            f'{numbered_context}\n\n'
            f'Student question:\n{query}\n\n'
            'Answer the question using the context above. Cite supporting '
            'context with bracketed numbers like [1] or [2] that match the '
            'numbered entries. If the context is insufficient, say so plainly.'
        )

        if stream:
            return self.generate_stream(
                prompt=prompt,
                system=system_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                history=history,
            )

        answer = self.generate(
            prompt=prompt,
            system=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            history=history,
        )
        return {
            'answer': answer,
            'sources': context_chunks,
            'model': model or self._model,
            'timestamp': timezone.now().isoformat(),
        }

    # ---------------------------------------------------------------- RAG (streaming, accumulating)

    def stream_with_context(
        self,
        query: str,
        context_chunks: List[str],
        system_prompt: str,
        *,
        on_token: Optional[Callable[[str], None]] = None,
        model: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Stream + accumulate. Yields via `on_token` and returns the full dict.

        Convenience wrapper for view code that wants to forward tokens to an
        SSE stream *and* persist the complete answer at the end. If `on_token`
        raises, we re-raise so the caller can close the stream gracefully.
        """
        gen = self.generate_with_context(
            query=query,
            context_chunks=context_chunks,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            history=history,
            stream=True,
        )
        pieces: List[str] = []
        for piece in gen:  # type: ignore[union-attr]
            pieces.append(piece)
            if on_token is not None:
                on_token(piece)
        return {
            'answer': ''.join(pieces),
            'sources': context_chunks,
            'model': model or self._model,
            'timestamp': timezone.now().isoformat(),
        }
