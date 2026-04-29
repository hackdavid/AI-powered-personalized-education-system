import logging

from apps.service.models import ContentNode, Asset
from apps.service.services.ingestion.latex_utils import latex_to_plain

logger = logging.getLogger(__name__)


class ContentStorage:
    """Stores content nodes in PostgreSQL tree + ChromaDB vector fallback."""

    def __init__(self):
        self._embedder = None
        self._vector_client = None

    def store(self, document, subject, nodes: list[dict], assets: list[dict]):
        """Store all nodes and their assets. Create embeddings for fallback."""
        if not nodes:
            logger.warning("No nodes to store")
            return

        node_map = {}

        # First pass: create all nodes (need PKs for parent FK)
        for i, node_data in enumerate(nodes):
            content_text = node_data.get("content", "")
            content_node = ContentNode.objects.create(
                tenant=document.tenant,
                document=document,
                parent=None,  # set in second pass
                subject=subject,
                node_id=node_data.get("id", f"node_{i}"),
                node_type=node_data.get("node_type", "topic"),
                title=node_data.get("title", "")[:500],
                content=content_text,
                content_plain=latex_to_plain(content_text),
                page_number=node_data.get("page_number"),
                difficulty=node_data.get("difficulty"),
                position=i,
                metadata=node_data.get("metadata", {}),
            )
            node_map[node_data.get("id")] = content_node

        # Second pass: set parent FK
        for node_data in nodes:
            parent_id = node_data.get("parent_id")
            node_id = node_data.get("id")
            if parent_id and parent_id in node_map and node_id in node_map:
                node = node_map[node_id]
                node.parent = node_map[parent_id]
                node.save()

        # Create assets linked to nodes
        asset_count = 0
        for node_data in nodes:
            for img in node_data.get("images", []):
                if img.get("linked") and node_data.get("id") in node_map:
                    parent_node = node_map[node_data["id"]]
                    Asset.objects.create(
                        tenant=document.tenant,
                        document=document,
                        content_node=parent_node,
                        asset_type="image",
                        file=img["file_path"],
                        description=img.get("description", ""),
                        caption=img.get("label", ""),
                        page_number=node_data.get("page_number"),
                        asset_ref_id=img.get("reference_id", ""),
                    )
                    asset_count += 1

            for tbl in node_data.get("tables", []):
                if node_data.get("id") in node_map:
                    parent_node = node_map[node_data["id"]]
                    Asset.objects.create(
                        tenant=document.tenant,
                        document=document,
                        content_node=parent_node,
                        asset_type="table",
                        description=tbl.get("description", ""),
                        structured_data={"markdown": tbl.get("markdown", "")},
                        page_number=node_data.get("page_number"),
                        asset_ref_id=f"{node_data['id']}_table",
                    )
                    asset_count += 1

        logger.info(f"Stored {len(node_map)} nodes and {asset_count} assets")

        # Embed content_plain into ChromaDB for fallback
        self._embed_nodes(document, subject, node_map)

    def _embed_nodes(self, document, subject, node_map):
        """Embed each node's plain text and store in ChromaDB."""
        try:
            from clients.embeddings import get_embedding_service
            from clients.vector_store import VectorStoreClient

            embedder = get_embedding_service()
            vector_client = VectorStoreClient()

            collection = vector_client.get_or_create_collection(
                tenant_id=str(document.tenant_id),
                name=f"subject_{subject.id}",
            )

            texts = []
            ids = []
            metadatas = []
            for node_id, node in node_map.items():
                if node.content_plain:
                    texts.append(node.content_plain)
                    ids.append(f"node_{node.id}")
                    metadatas.append({
                        "node_id": node.node_id,
                        "node_type": node.node_type,
                        "title": node.title,
                    })

            if texts:
                vector_client.add_documents(collection, texts, metadatas, ids)
                # Store embedding IDs back on nodes
                for node in node_map.values():
                    if node.content_plain:
                        node.embedding_id = f"node_{node.id}"
                        ContentNode.objects.filter(id=node.id).update(
                            embedding_id=f"node_{node.id}"
                        )
                logger.info(f"Embedded {len(texts)} nodes in ChromaDB")

        except Exception as e:
            logger.warning(f"Embedding failed (non-critical): {e}")
