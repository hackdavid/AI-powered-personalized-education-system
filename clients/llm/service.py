"""
OpenAI-compatible LLM service.
Supports any OpenAI-compatible API via configurable base_url (OpenAI, Azure, Ollama, etc.).
"""

import logging
from typing import Dict, List, Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class LLMService:
    """LLM client using the OpenAI Python SDK with configurable base_url."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self._base_url = base_url or getattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")
        self._api_key = api_key or getattr(settings, "OPENAI_API_KEY", "")
        self._model_name = model_name or getattr(settings, "OPENAI_MODEL_NAME", "gpt-4")
        self._client = None

    @property
    def client(self):
        """Lazy-initialize the OpenAI client on first use."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
            )
            logger.debug(f"LLM client initialized: base_url={self._base_url}, model={self._model_name}")
        return self._client

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate a text completion from a single prompt."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content

    def generate_with_context(
        self,
        query: str,
        context_chunks: List[str],
        system_prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.5,
    ) -> Dict:
        """RAG-style generation: answer a query using retrieved context chunks with source citation."""
        numbered_context = "\n\n".join(
            f"[{i + 1}] {chunk}" for i, chunk in enumerate(context_chunks)
        )

        prompt = (
            f"Context from curriculum materials:\n"
            f"{numbered_context}\n\n"
            f"Student question: {query}\n\n"
            "Provide a helpful answer based ONLY on the context above. "
            "Cite sources using [1], [2], etc."
        )

        answer = self.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=temperature,
        )

        return {
            "answer": answer,
            "sources": context_chunks,
            "model": self._model_name,
            "timestamp": timezone.now().isoformat(),
        }
