"""
Local ChromaDB vector store client.
Uses PersistentClient for data that survives restarts — no separate server needed.
"""

import logging
import uuid
from typing import Dict, List, Optional

import chromadb
from django.conf import settings

from services.ai.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


class VectorStoreClient:
    """Manages vector collections and similarity search using local ChromaDB."""

    def __init__(self, persist_dir: Optional[str] = None):
        self._persist_dir = persist_dir or getattr(settings, "CHROMADB_PERSIST_DIR", "chroma_data")
        self._client: Optional[chromadb.PersistentClient] = None
        self._embedding_service = None

    @property
    def client(self) -> chromadb.PersistentClient:
        """Lazy-init the ChromaDB persistent client."""
        if self._client is None:
            self._client = chromadb.PersistentClient(path=self._persist_dir)
            logger.debug(f"ChromaDB client initialized at: {self._persist_dir}")
        return self._client

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def get_or_create_collection(self, tenant_id: str, name: str) -> chromadb.Collection:
        """Get or create a tenant-scoped collection."""
        full_name = f"{tenant_id}_{name}"
        return self.client.get_or_create_collection(
            name=full_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(
        self,
        collection: chromadb.Collection,
        documents: List[str],
        metadatas: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ) -> int:
        """Embed and store documents in a collection. Returns count added."""
        embeddings = self.embedding_service.embed_batch(documents)
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in documents]

        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas or [{}] * len(documents),
        )
        logger.info(f"Added {len(documents)} documents to collection '{collection.name}'")
        return len(documents)

    def search(
        self,
        collection: chromadb.Collection,
        query: str,
        top_k: int = 5,
    ) -> List[Dict]:
        """Semantic search: embed the query and find the closest documents."""
        query_embedding = self.embedding_service.embed_text(query)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        if results and results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                hits.append({
                    "text": doc,
                    "metadata": meta,
                    "score": 1 - dist,  # convert cosine distance to similarity
                })
        return hits

    def delete_documents(self, collection: chromadb.Collection, ids: List[str]) -> None:
        """Remove documents by their IDs."""
        collection.delete(ids=ids)
        logger.info(f"Deleted {len(ids)} documents from collection '{collection.name}'")

    def get_collection_stats(self, collection: chromadb.Collection) -> Dict:
        """Return basic stats for a collection."""
        count = collection.count()
        peek = collection.peek(limit=3)
        return {
            "name": collection.name,
            "count": count,
            "sample_ids": peek.get("ids", []),
        }

    def list_collections(self) -> List[str]:
        """List all collection names in the vector store."""
        return [c.name for c in self.client.list_collections()]

    def delete_collection(self, tenant_id: str, name: str) -> None:
        """Delete an entire collection."""
        full_name = f"{tenant_id}_{name}"
        self.client.delete_collection(full_name)
        logger.info(f"Deleted collection '{full_name}'")
