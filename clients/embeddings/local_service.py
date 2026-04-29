"""
Local embedding service using sentence-transformers.

This is the fallback / offline implementation. The remote client at
`clients.embeddings.remote_client` is the default in dev + production
because installing torch reliably across the team is painful. Pick which
one to use via `EMBEDDING_PROVIDER` in settings.

If you do want to use this locally, install the optional extras:

    pip install -r requirements/embeddings-local.txt
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

_model = None
_model_name = None


def init_model(model_name: str = "all-MiniLM-L6-v2"):
    """Pre-load the embedding model. Idempotent. Optional — the service
    will lazy-load on first call if you forget."""
    global _model, _model_name
    if _model is not None:
        return
    logger.info("Loading sentence-transformers model: %s ...", model_name)
    from sentence_transformers import SentenceTransformer  # heavy import, lazy on purpose
    _model = SentenceTransformer(model_name)
    _model_name = model_name
    logger.info(
        "Embedding model loaded: %s (dim=%d)",
        model_name,
        _model.get_sentence_embedding_dimension(),
    )


class LocalEmbeddingService:
    """Generates embeddings using a locally-loaded sentence-transformers model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        if _model is None:
            init_model(model_name)
        self._model = _model
        self._model_name = _model_name

    def embed_text(self, text: str) -> List[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self._model.encode(texts, normalize_embeddings=True, batch_size=64).tolist()

    def get_embedding_dimension(self) -> int:
        return self._model.get_sentence_embedding_dimension()

    @property
    def model_name(self) -> str:
        return self._model_name


# Backwards-compatible alias. New code should import LocalEmbeddingService.
EmbeddingService = LocalEmbeddingService


_embedding_service: LocalEmbeddingService | None = None


def get_embedding_service() -> LocalEmbeddingService:
    """Return a reusable singleton LocalEmbeddingService instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = LocalEmbeddingService()
    return _embedding_service
