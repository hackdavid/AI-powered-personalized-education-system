"""
Unit tests for the RemoteEmbeddingService HTTP client.

`requests.Session.request` is mocked everywhere so tests run with no
network access and no torch install.
"""

from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings


def _mock_response(status_code: int = 200, json_payload=None, text: str = ""):
    """Build a realistic-enough mock for `requests.Response`."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 400
    resp.text = text or (str(json_payload) if json_payload is not None else "")
    resp.json.return_value = json_payload if json_payload is not None else {}
    return resp


@override_settings(
    EMBEDDER_API_URL="https://example.test",
    EMBEDDER_API_KEY="test-key",
    EMBEDDING_PROVIDER="remote",
)
class RemoteEmbeddingServiceTests(SimpleTestCase):
    """All tests live under SimpleTestCase — no DB, no migrations."""

    def setUp(self):
        # Reset the module-level singleton between tests to avoid cross-pollution
        # with cached metadata.
        from clients.embeddings import remote_client
        remote_client._remote_service = None

    # --------------------------------------------------------------- happy paths

    @patch("requests.Session.request")
    def test_embed_text_returns_vector_and_caches_metadata(self, mock_req):
        from clients.embeddings.remote_client import RemoteEmbeddingService
        mock_req.return_value = _mock_response(200, {
            "embedding": [0.1, 0.2, 0.3],
            "model": "all-MiniLM-L6-v2",
            "dim": 384,
        })
        svc = RemoteEmbeddingService()
        out = svc.embed_text("hello")

        self.assertEqual(out, [0.1, 0.2, 0.3])
        # Cached: subsequent property reads must NOT trigger a new request
        self.assertEqual(svc.model_name, "all-MiniLM-L6-v2")
        self.assertEqual(svc.get_embedding_dimension(), 384)
        self.assertEqual(mock_req.call_count, 1)

        called_kwargs = mock_req.call_args.kwargs
        self.assertEqual(mock_req.call_args.args[0], "post")
        self.assertEqual(mock_req.call_args.args[1], "https://example.test/embed_one")
        self.assertEqual(called_kwargs["json"], {"text": "hello"})

    @patch("requests.Session.request")
    def test_embed_batch_returns_list_of_vectors(self, mock_req):
        from clients.embeddings.remote_client import RemoteEmbeddingService
        mock_req.return_value = _mock_response(200, {
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
            "model": "m",
            "dim": 2,
        })
        out = RemoteEmbeddingService().embed_batch(["a", "b"])

        self.assertEqual(out, [[0.1, 0.2], [0.3, 0.4]])
        self.assertEqual(mock_req.call_args.args[1], "https://example.test/embed")
        self.assertEqual(mock_req.call_args.kwargs["json"], {"texts": ["a", "b"]})

    @patch("requests.Session.request")
    def test_embed_batch_empty_short_circuits(self, mock_req):
        from clients.embeddings.remote_client import RemoteEmbeddingService
        out = RemoteEmbeddingService().embed_batch([])
        self.assertEqual(out, [])
        mock_req.assert_not_called()

    @patch("requests.Session.request")
    def test_health_caches_metadata_for_lazy_property_access(self, mock_req):
        from clients.embeddings.remote_client import RemoteEmbeddingService
        mock_req.return_value = _mock_response(200, {
            "status": "ok", "model": "all-MiniLM-L6-v2", "dim": 384,
        })
        svc = RemoteEmbeddingService()
        self.assertEqual(svc.model_name, "all-MiniLM-L6-v2")
        self.assertEqual(svc.get_embedding_dimension(), 384)
        # Both reads share one /health call
        self.assertEqual(mock_req.call_count, 1)
        self.assertEqual(mock_req.call_args.args[0], "get")
        self.assertEqual(mock_req.call_args.args[1], "https://example.test/health")

    # --------------------------------------------------------------- auth / errors

    @patch("requests.Session.request")
    def test_401_raises_friendly_error(self, mock_req):
        from clients.embeddings.remote_client import EmbeddingClientError, RemoteEmbeddingService
        mock_req.return_value = _mock_response(401, {"detail": "Invalid or missing API key."})

        with self.assertRaises(EmbeddingClientError) as ctx:
            RemoteEmbeddingService().embed_text("x")
        self.assertIn("API key", str(ctx.exception))
        # No retries on 401
        self.assertEqual(mock_req.call_count, 1)

    @patch("requests.Session.request")
    def test_403_raises_immediately(self, mock_req):
        from clients.embeddings.remote_client import EmbeddingClientError, RemoteEmbeddingService
        mock_req.return_value = _mock_response(403, {"detail": "forbidden"})
        with self.assertRaises(EmbeddingClientError):
            RemoteEmbeddingService().embed_text("x")
        self.assertEqual(mock_req.call_count, 1)

    @patch("clients.embeddings.remote_client.time.sleep")  # skip real sleeps
    @patch("requests.Session.request")
    def test_503_then_200_succeeds_via_retry(self, mock_req, _sleep):
        from clients.embeddings.remote_client import RemoteEmbeddingService
        mock_req.side_effect = [
            _mock_response(503, text="cold start"),
            _mock_response(200, {
                "embedding": [0.5], "model": "m", "dim": 1,
            }),
        ]
        out = RemoteEmbeddingService().embed_text("warm me up")
        self.assertEqual(out, [0.5])
        self.assertEqual(mock_req.call_count, 2)

    @patch("clients.embeddings.remote_client.time.sleep")
    @patch("requests.Session.request")
    def test_persistent_500_exhausts_retries(self, mock_req, _sleep):
        from clients.embeddings.remote_client import EmbeddingClientError, RemoteEmbeddingService
        mock_req.return_value = _mock_response(500, text="boom")
        with self.assertRaises(EmbeddingClientError) as ctx:
            RemoteEmbeddingService().embed_text("x")
        self.assertIn("unreachable", str(ctx.exception))
        self.assertEqual(mock_req.call_count, 3)  # DEFAULT_RETRIES

    @patch("clients.embeddings.remote_client.time.sleep")
    @patch("requests.Session.request")
    def test_connection_error_retries_then_fails(self, mock_req, _sleep):
        from clients.embeddings.remote_client import EmbeddingClientError, RemoteEmbeddingService
        mock_req.side_effect = requests.ConnectionError("dns down")
        with self.assertRaises(EmbeddingClientError):
            RemoteEmbeddingService().embed_text("x")
        self.assertEqual(mock_req.call_count, 3)

    # --------------------------------------------------------------- config

    @override_settings(EMBEDDER_API_URL="")
    def test_missing_api_url_raises_clearly(self):
        from clients.embeddings.remote_client import EmbeddingClientError, RemoteEmbeddingService
        with self.assertRaises(EmbeddingClientError) as ctx:
            RemoteEmbeddingService()
        self.assertIn("EMBEDDER_API_URL", str(ctx.exception))

    @patch("requests.Session.request")
    def test_api_key_sent_as_header(self, mock_req):
        from clients.embeddings.remote_client import RemoteEmbeddingService
        mock_req.return_value = _mock_response(200, {
            "embedding": [0.1], "model": "m", "dim": 1,
        })
        svc = RemoteEmbeddingService()
        svc.embed_text("x")
        # Header is set on the Session, not the per-request kwargs
        self.assertEqual(svc._session.headers.get("X-API-Key"), "test-key")


# ----------------------------------------------------------------- factory


class FactoryTests(SimpleTestCase):
    """The clients.embeddings.__init__ factory routes to local vs remote."""

    @override_settings(
        EMBEDDING_PROVIDER="remote",
        EMBEDDER_API_URL="https://example.test",
        EMBEDDER_API_KEY="k",
    )
    def test_factory_returns_remote_by_default(self):
        # reset both singletons so the factory builds a fresh instance
        from clients.embeddings import remote_client
        remote_client._remote_service = None

        from clients.embeddings import get_embedding_service
        from clients.embeddings.remote_client import RemoteEmbeddingService
        svc = get_embedding_service()
        self.assertIsInstance(svc, RemoteEmbeddingService)

    @override_settings(EMBEDDING_PROVIDER="remote")
    def test_init_model_is_noop_for_remote(self):
        from clients.embeddings import init_model
        # must not raise even though sentence-transformers may not be installed
        init_model("any-model")
