"""
Tests for the pgvector-backed `VectorStoreClient`.

We mock the embedding service (no network) and the `pgvector.django`
distance call (no real vector math), and exercise the facade + ORM
shape against SQLite's in-memory test DB. The goal is to lock in the
ChromaDB-compatible public surface (`get_or_create_collection`,
`add_documents`, `search`, `delete_documents`, `_Collection.delete`,
etc.) so downstream callers keep working.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.accounts.models import Role, Tenant
from apps.service.models import (
    ContentEmbedding,
    ContentNode,
    Document,
    Subject,
)
from clients.vector_store import VectorStoreClient
from clients.vector_store.client import _Collection


def _mk_embedding_service(dim: int = 384):
    """Return a MagicMock shaped like `EmbeddingService`."""
    svc = MagicMock()
    svc.embed_text.return_value = [0.1] * dim
    svc.embed_batch.side_effect = lambda texts: [[0.1] * dim for _ in texts]
    svc.get_embedding_dimension.return_value = dim
    svc.model_name = "all-MiniLM-L6-v2"
    return svc


def _bootstrap_tenant(slug="acme") -> Tenant:
    for code in (Role.STUDENT, Role.TEACHER, Role.SCHOOL_ADMIN):
        Role.objects.get_or_create(
            name=code,
            defaults={"display_name": code.title(), "level": 50},
        )
    tenant, _ = Tenant.objects.get_or_create(slug=slug, defaults={"name": slug.title(), "is_active": True})
    return tenant


def _mk_content_node(tenant, subject, document, node_id="ch1.s1.t1", title="Topic"):
    return ContentNode.objects.create(
        tenant=tenant,
        document=document,
        subject=subject,
        node_id=node_id,
        node_type="topic",
        title=title,
        content="content text",
        content_plain="content text",
        position=1,
    )


class CollectionHandleTests(TestCase):
    """`_Collection` is a thin routing struct — verify the small surface."""

    def setUp(self):
        self.tenant = _bootstrap_tenant()
        self.vs = VectorStoreClient()

    def test_get_or_create_collection_carries_tenant_id_and_name(self):
        col = self.vs.get_or_create_collection(str(self.tenant.id), "curriculum")
        self.assertIsInstance(col, _Collection)
        self.assertEqual(col.tenant_id, str(self.tenant.id))
        self.assertEqual(col.name, "curriculum")

    def test_collection_tenant_id_is_stringified(self):
        col = self.vs.get_or_create_collection(self.tenant.id, "curriculum")
        self.assertEqual(col.tenant_id, str(self.tenant.id))

    def test_collection_delete_shim_calls_client_delete_documents(self):
        col = self.vs.get_or_create_collection(str(self.tenant.id), "curriculum")
        with patch.object(self.vs, "delete_documents") as mock_delete:
            col.delete(ids=["a", "b"])
        mock_delete.assert_called_once_with(col, ["a", "b"])

    def test_collection_count_reflects_tenant_rows(self):
        col = self.vs.get_or_create_collection(str(self.tenant.id), "curriculum")
        self.assertEqual(col.count(), 0)


class AddDocumentsTests(TestCase):
    """`add_documents` embeds then bulk-inserts `ContentEmbedding` rows."""

    def setUp(self):
        self.tenant = _bootstrap_tenant("springfield")
        self.subject = Subject.objects.create(
            tenant=self.tenant, code="MATH", name="Mathematics", is_active=True,
        )
        self.document = Document.objects.create(
            tenant=self.tenant, title="Math G8",
            source_type=Document.SourceType.SYNTHETIC, subject=self.subject,
        )
        self.node = _mk_content_node(self.tenant, self.subject, self.document)
        self.vs = VectorStoreClient()
        self.vs._embedding_service = _mk_embedding_service()

    def _collection(self):
        return self.vs.get_or_create_collection(str(self.tenant.id), "curriculum")

    def test_empty_batch_returns_zero_without_embedder_call(self):
        col = self._collection()
        added = self.vs.add_documents(col, documents=[], metadatas=[], ids=[])
        self.assertEqual(added, 0)
        self.vs._embedding_service.embed_batch.assert_not_called()

    def test_adds_row_for_each_valid_metadata(self):
        col = self._collection()
        docs = ["body text"]
        metas = [{"document_id": self.document.id, "node_id": self.node.node_id}]
        ids = [f"{self.tenant.id}-{self.document.id}-{self.node.node_id}"]

        added = self.vs.add_documents(col, docs, metas, ids)

        self.assertEqual(added, 1)
        self.assertEqual(ContentEmbedding.objects.count(), 1)
        row = ContentEmbedding.objects.first()
        self.assertEqual(row.tenant_id, self.tenant.id)
        self.assertEqual(row.content_node_id, self.node.id)
        self.assertEqual(row.model_name, "all-MiniLM-L6-v2")
        self.assertEqual(row.embedding_id, ids[0])

    def test_metadata_without_node_id_is_skipped(self):
        col = self._collection()
        added = self.vs.add_documents(
            col,
            documents=["x", "y"],
            metadatas=[{"document_id": self.document.id, "node_id": self.node.node_id}, {}],
            ids=["id-1", "id-2"],
        )
        self.assertEqual(added, 1)
        self.assertEqual(ContentEmbedding.objects.count(), 1)

    def test_dimension_mismatch_raises(self):
        col = self._collection()
        # Embedder returns wrong-dim vectors
        self.vs._embedding_service.embed_batch.side_effect = lambda texts: [[0.1] * 768 for _ in texts]
        with self.assertRaises(ValueError) as ctx:
            self.vs.add_documents(
                col,
                documents=["x"],
                metadatas=[{"document_id": self.document.id, "node_id": self.node.node_id}],
                ids=["id-x"],
            )
        self.assertIn("768", str(ctx.exception))

    def test_rerun_replaces_existing_row_for_same_node_and_model(self):
        col = self._collection()
        meta = {"document_id": self.document.id, "node_id": self.node.node_id}
        self.vs.add_documents(col, ["v1"], [meta], ["id-1"])
        self.assertEqual(ContentEmbedding.objects.count(), 1)

        # Re-embed with a different id/content; should NOT duplicate because
        # (content_node, model_name) is unique_together.
        self.vs.add_documents(col, ["v2"], [meta], ["id-2"])
        self.assertEqual(ContentEmbedding.objects.count(), 1)
        self.assertEqual(ContentEmbedding.objects.first().embedding_id, "id-2")

    def test_only_own_tenant_rows_are_touched(self):
        col = self._collection()
        other_tenant = _bootstrap_tenant("riverside")
        other_subject = Subject.objects.create(
            tenant=other_tenant, code="MATH", name="Mathematics", is_active=True,
        )
        other_doc = Document.objects.create(
            tenant=other_tenant, title="Math G8",
            source_type=Document.SourceType.SYNTHETIC, subject=other_subject,
        )
        other_node = _mk_content_node(other_tenant, other_subject, other_doc, node_id="ch1.s1.t1")
        # Pre-existing embedding for the OTHER tenant
        ContentEmbedding.objects.create(
            tenant=other_tenant,
            content_node=other_node,
            embedding=[0.9] * 384,
            model_name="all-MiniLM-L6-v2",
            embedding_id="other-id",
        )
        self.assertEqual(ContentEmbedding.objects.count(), 1)

        # Insert for our tenant — the other tenant's row must be untouched.
        self.vs.add_documents(
            col,
            documents=["text"],
            metadatas=[{"document_id": self.document.id, "node_id": self.node.node_id}],
            ids=["ours"],
        )
        self.assertEqual(ContentEmbedding.objects.count(), 2)
        self.assertTrue(
            ContentEmbedding.objects.filter(tenant=other_tenant, embedding_id="other-id").exists()
        )


class SearchTests(TestCase):
    """`search` mocks `CosineDistance` annotation — we verify call shape."""

    def setUp(self):
        self.tenant = _bootstrap_tenant()
        self.vs = VectorStoreClient()
        self.vs._embedding_service = _mk_embedding_service()

    def _collection(self):
        return self.vs.get_or_create_collection(str(self.tenant.id), "curriculum")

    def test_empty_query_returns_empty_without_embedder_call(self):
        hits = self.vs.search(self._collection(), "   ", top_k=5)
        self.assertEqual(hits, [])
        self.vs._embedding_service.embed_text.assert_not_called()

    @patch("pgvector.django.CosineDistance")
    def test_search_filters_by_tenant_and_orders_by_distance(self, mock_cos):
        # Fake CosineDistance: returns an annotation that Django can order by.
        # Returns a constant so SQLite can execute the query without pgvector.
        from django.db.models import Value, FloatField
        mock_cos.return_value = Value(0.0, output_field=FloatField())

        hits = self.vs.search(self._collection(), "what is a quadratic?", top_k=3)

        self.vs._embedding_service.embed_text.assert_called_once_with("what is a quadratic?")
        mock_cos.assert_called_once()
        # First positional arg is the field name 'embedding'
        self.assertEqual(mock_cos.call_args.args[0], "embedding")
        # Second positional arg is the query vector (384 floats)
        self.assertEqual(len(mock_cos.call_args.args[1]), 384)
        # No embeddings exist yet → empty hits but no crash
        self.assertEqual(hits, [])


class DeleteAndListingTests(TestCase):
    """Admin helpers: delete_documents, list_collections, delete_collection."""

    def setUp(self):
        self.tenant = _bootstrap_tenant("t1")
        self.subject = Subject.objects.create(
            tenant=self.tenant, code="MATH", name="Mathematics", is_active=True,
        )
        self.document = Document.objects.create(
            tenant=self.tenant, title="Math G8",
            source_type=Document.SourceType.SYNTHETIC, subject=self.subject,
        )
        self.node = _mk_content_node(self.tenant, self.subject, self.document)
        self.vs = VectorStoreClient()

        ContentEmbedding.objects.create(
            tenant=self.tenant,
            content_node=self.node,
            embedding=[0.1] * 384,
            model_name="all-MiniLM-L6-v2",
            embedding_id="t1-1",
        )

    def test_delete_documents_removes_matching_embedding_ids(self):
        col = self.vs.get_or_create_collection(str(self.tenant.id))
        self.vs.delete_documents(col, ids=["t1-1"])
        self.assertEqual(ContentEmbedding.objects.filter(tenant=self.tenant).count(), 0)

    def test_delete_documents_noop_on_unknown_ids(self):
        col = self.vs.get_or_create_collection(str(self.tenant.id))
        self.vs.delete_documents(col, ids=["does-not-exist"])
        self.assertEqual(ContentEmbedding.objects.filter(tenant=self.tenant).count(), 1)

    def test_list_collections_returns_tenant_suffixed_names(self):
        names = self.vs.list_collections()
        self.assertIn(f"{self.tenant.id}_curriculum", names)

    def test_delete_collection_clears_all_tenant_rows(self):
        self.vs.delete_collection(str(self.tenant.id))
        self.assertEqual(ContentEmbedding.objects.filter(tenant=self.tenant).count(), 0)

    def test_get_collection_stats_reports_count_and_name(self):
        col = self.vs.get_or_create_collection(str(self.tenant.id), "curriculum")
        stats = self.vs.get_collection_stats(col)
        self.assertEqual(stats["count"], 1)
        self.assertIn(f"{self.tenant.id}_curriculum", stats["name"])
