"""
Remote embedding service client.

Talks HTTP to the `eduai-embedder` HuggingFace Space (or any compatible
service). Default provider in dev + prod — keeps `torch` out of the
platform's `requirements/base.txt` so a fresh `pip install` works on
Windows + Conda without DLL fights.

Public surface mirrors `clients.embeddings.local_service.LocalEmbeddingService`
so callers (`CurriculumRetriever`, `VectorStoreClient`, ingestion stages)
stay provider-agnostic.

Wire-up: set in `eduai_platform/.env`

    EMBEDDING_PROVIDER=remote
    EMBEDDER_API_URL=https://<user>-<space>.hf.space
    EMBEDDER_API_KEY=<32-char-token>

The service:
- Caches `model_name` and `dim` from a single `/health` round-trip on
  first use, so subsequent property accesses are zero-cost.
- Retries idempotent 5xx + transient connection errors with exponential
  backoff (3 attempts, 0.5s/1s/2s).
- Times out at 30 s — generous because the free HF Space has a ~30 s
  cold-start after sleeping.
- Raises `EmbeddingClientError` (a plain `RuntimeError` subclass) on
  permanent failures so callers can degrade gracefully.
"""

import logging
import time
from typing import List, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class EmbeddingClientError(RuntimeError):
    """Raised when the remote embedder cannot be reached or returns an error."""


DEFAULT_TIMEOUT = 30  # seconds — covers HF Space cold start
DEFAULT_RETRIES = 3
RETRY_BACKOFF = (0.5, 1.0, 2.0)
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}


class RemoteEmbeddingService:
    """HTTP client for the eduai-embedder service."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self._api_url = (api_url or getattr(settings, "EMBEDDER_API_URL", "")).rstrip("/")
        self._api_key = api_key or getattr(settings, "EMBEDDER_API_KEY", "") or ""
        self._timeout = timeout

        if not self._api_url:
            raise EmbeddingClientError(
                "EMBEDDER_API_URL is not configured. Set EMBEDDING_PROVIDER=local "
                "or supply EMBEDDER_API_URL (and EMBEDDER_API_KEY) in your .env."
            )

        # Cached after first call (either explicit or via /health).
        self._model_name: Optional[str] = model_name
        self._dim: Optional[int] = None

        self._session = requests.Session()
        if self._api_key:
            self._session.headers.update({"X-API-Key": self._api_key})
        self._session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------ public API

    def embed_text(self, text: str) -> List[float]:
        data = self._post("/embed_one", {"text": text})
        self._cache_metadata(data)
        return data["embedding"]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        data = self._post("/embed", {"texts": list(texts)})
        self._cache_metadata(data)
        return data["embeddings"]

    def get_embedding_dimension(self) -> int:
        if self._dim is None:
            self._fetch_health()
        return self._dim or 0

    @property
    def model_name(self) -> str:
        if self._model_name is None:
            self._fetch_health()
        return self._model_name or ""

    def health(self) -> dict:
        """Public health check — returns the raw `/health` payload."""
        return self._fetch_health()

    # ------------------------------------------------------------------ internals

    def _cache_metadata(self, payload: dict) -> None:
        if self._model_name is None and payload.get("model"):
            self._model_name = payload["model"]
        if self._dim is None and payload.get("dim"):
            self._dim = int(payload["dim"])

    def _fetch_health(self) -> dict:
        """Call /health (no auth required), update cached metadata, return payload."""
        url = f"{self._api_url}/health"
        resp = self._request_with_retry("get", url)
        try:
            data = resp.json()
        except ValueError as exc:
            raise EmbeddingClientError(f"Invalid JSON from /health: {exc}") from exc
        self._cache_metadata(data)
        return data

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._api_url}{path}"
        resp = self._request_with_retry("post", url, json=body)
        try:
            return resp.json()
        except ValueError as exc:
            raise EmbeddingClientError(f"Invalid JSON from {path}: {exc}") from exc

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(DEFAULT_RETRIES):
            try:
                resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                logger.warning(
                    "Embedder request transport error (attempt %d/%d): %s",
                    attempt + 1, DEFAULT_RETRIES, exc,
                )
                self._sleep_for_retry(attempt)
                continue

            if resp.status_code == 401:
                raise EmbeddingClientError(
                    "Embedder rejected the API key (401). "
                    "Check EMBEDDER_API_KEY against the Space's secret."
                )
            if resp.status_code == 403:
                raise EmbeddingClientError("Embedder forbade the request (403).")
            if resp.status_code in RETRYABLE_STATUSES:
                logger.warning(
                    "Embedder returned %d (attempt %d/%d) — retrying.",
                    resp.status_code, attempt + 1, DEFAULT_RETRIES,
                )
                last_exc = EmbeddingClientError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                self._sleep_for_retry(attempt)
                continue
            if not resp.ok:
                raise EmbeddingClientError(
                    f"Embedder error {resp.status_code}: {resp.text[:200]}"
                )
            return resp

        # Exhausted retries
        raise EmbeddingClientError(
            f"Embedder unreachable after {DEFAULT_RETRIES} attempts: {last_exc}"
        ) from last_exc

    @staticmethod
    def _sleep_for_retry(attempt: int) -> None:
        if attempt + 1 < DEFAULT_RETRIES:
            delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            time.sleep(delay)


# Module-level singleton — mirrors the local_service contract.
_remote_service: Optional[RemoteEmbeddingService] = None


def get_embedding_service() -> RemoteEmbeddingService:
    """Return a reusable singleton RemoteEmbeddingService instance."""
    global _remote_service
    if _remote_service is None:
        _remote_service = RemoteEmbeddingService()
    return _remote_service


def init_model(model_name: Optional[str] = None) -> None:
    """No-op for the remote provider; kept so callers can stay provider-agnostic."""
    return None
