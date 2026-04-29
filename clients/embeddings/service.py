"""
Free embedding service using sentence-transformers.
Model is loaded once at server startup via services.apps.ServicesConfig.ready().
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

_model = None
_model_name = None


def init_model(model_name: str = "all-MiniLM-L6-v2"):
    """Pre-load the embedding model. Called from AppConfig.ready()."""
    global _model, _model_name
    if _model is not None:
        return
    logger.info(f"Loading embedding model: {model_name} ...")
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer(model_name)
    _model_name = model_name
    logger.info(f"Embedding model loaded: {model_name} (dim={_model.get_sentence_embedding_dimension()})")


class EmbeddingService:
    """Generates embeddings using a locally-loaded sentence-transformers model."""

    def __init__(self):
        if _model is None:
            raise RuntimeError(
                "Embedding model not loaded. Ensure 'services' app is in INSTALLED_APPS "
                "and the Django app registry has finished loading."
            )
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


# Module-level convenience singleton (created after model init)
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Return a reusable EmbeddingService instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
