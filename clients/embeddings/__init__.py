"""
Embedding client factory.

Routes `get_embedding_service()` and `init_model()` to either the local
sentence-transformers implementation or the remote HuggingFace Space
client based on `settings.EMBEDDING_PROVIDER`.

Default provider is `remote` so a fresh `pip install` on Windows / Mac /
Linux works without `torch`. Set `EMBEDDING_PROVIDER=local` and install
`requirements/embeddings-local.txt` if you want the in-process model.

Public API (provider-agnostic):

    from clients.embeddings import get_embedding_service, init_model
    embedder = get_embedding_service()
    embedder.embed_text("hello")
    embedder.embed_batch(["hi", "hello"])
    embedder.get_embedding_dimension()
    embedder.model_name
"""

from typing import Protocol, runtime_checkable, List

from django.conf import settings


@runtime_checkable
class EmbeddingService(Protocol):
    """Duck-typed interface implemented by both local + remote providers."""

    def embed_text(self, text: str) -> List[float]: ...
    def embed_batch(self, texts: List[str]) -> List[List[float]]: ...
    def get_embedding_dimension(self) -> int: ...

    @property
    def model_name(self) -> str: ...


def _provider() -> str:
    return (getattr(settings, "EMBEDDING_PROVIDER", "remote") or "remote").lower()


def get_embedding_service() -> EmbeddingService:
    """Return the configured embedding service singleton."""
    if _provider() == "local":
        from .local_service import get_embedding_service as _get_local
        return _get_local()
    from .remote_client import get_embedding_service as _get_remote
    return _get_remote()


def init_model(model_name: str = "all-MiniLM-L6-v2") -> None:
    """Pre-load / warm the configured provider. No-op for remote."""
    if _provider() == "local":
        from .local_service import init_model as _init_local
        _init_local(model_name)
        return
    # remote provider: no-op (pre-loading happens inside the HF Space).
    return None


__all__ = ["EmbeddingService", "get_embedding_service", "init_model"]
