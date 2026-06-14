"""
RAG Platform – unit & integration tests.
Run with: pytest tests/ -v
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, Response

# Patch out OpenTelemetry before importing app to avoid grpc setup in tests
with patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app"):
    from app.api.main import app, settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Synchronous test client (no lifespan startup)."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def mock_vector_store_healthy():
    """Patch httpx so vector store health returns 200."""
    async def mock_get(*args, **kwargs):
        r = MagicMock(spec=Response)
        r.status_code = 200
        return r

    with patch("httpx.AsyncClient.get", new=mock_get):
        yield


@pytest.fixture
def mock_vector_store_down():
    async def mock_get(*args, **kwargs):
        raise ConnectionRefusedError("connection refused")

    with patch("httpx.AsyncClient.get", new=mock_get):
        yield


# ---------------------------------------------------------------------------
# Health & Readiness
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client, mock_vector_store_healthy):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_schema(self, client, mock_vector_store_healthy):
        data = client.get("/health").json()
        assert "status" in data
        assert "version" in data
        assert "environment" in data
        assert "dependencies" in data
        assert data["status"] == "ok"

    def test_health_includes_app_version(self, client, mock_vector_store_healthy):
        data = client.get("/health").json()
        assert data["version"] == settings.app_version

    def test_health_vector_store_unreachable_still_200(self, client, mock_vector_store_down):
        # Liveness should not fail because a dep is down
        resp = client.get("/health")
        assert resp.status_code == 200
        assert client.get("/health").json()["dependencies"]["vector_store"] == "unreachable"


class TestReadinessEndpoint:
    def test_readyz_healthy(self, client, mock_vector_store_healthy):
        resp = client.get("/readyz")
        assert resp.status_code == 200

    def test_readyz_unhealthy_when_vector_store_down(self, client, mock_vector_store_down):
        resp = client.get("/readyz")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    def test_metrics_returns_text(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]

    def test_metrics_contains_rag_counters(self, client):
        resp = client.get("/metrics")
        assert b"rag_request_total" in resp.content


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------

class TestQueryEndpoint:
    def _make_embedding_response(self):
        mock = MagicMock(spec=Response)
        mock.status_code = 200
        mock.json.return_value = {
            "data": [{"embedding": [0.1] * 1536}]
        }
        return mock

    def _make_vector_search_response(self):
        mock = MagicMock(spec=Response)
        mock.status_code = 200
        mock.json.return_value = {
            "result": [
                {
                    "id": "doc-1",
                    "score": 0.92,
                    "payload": {"content": "Paris is the capital of France.", "metadata": {}},
                }
            ]
        }
        return mock

    def _make_llm_response(self):
        mock = MagicMock(spec=Response)
        mock.status_code = 200
        mock.json.return_value = {
            "choices": [{"message": {"content": "Paris is the capital of France."}}]
        }
        return mock

    def test_query_returns_answer(self, client):
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = [
                self._make_embedding_response(),
                self._make_vector_search_response(),
                self._make_llm_response(),
            ]
            resp = client.post("/query", json={"query": "What is the capital of France?"})

        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "sources" in data
        assert "query_id" in data
        assert "latency_ms" in data
        assert len(data["sources"]) == 1
        assert data["sources"][0]["score"] == 0.92

    def test_query_validates_empty_string(self, client):
        resp = client.post("/query", json={"query": ""})
        assert resp.status_code == 422

    def test_query_validates_too_long(self, client):
        resp = client.post("/query", json={"query": "x" * 3000})
        assert resp.status_code == 422

    def test_query_validates_top_k_bounds(self, client):
        resp = client.post("/query", json={"query": "hello", "top_k": 0})
        assert resp.status_code == 422
        resp = client.post("/query", json={"query": "hello", "top_k": 50})
        assert resp.status_code == 422

    def test_query_requires_body(self, client):
        resp = client.post("/query")
        assert resp.status_code == 422

    def test_query_404_when_no_docs_found(self, client):
        def side_effect(*args, **kwargs):
            url = str(args[0]) if args else str(kwargs.get("url", ""))
            if "embeddings" in url:
                return self._make_embedding_response()
            mock = MagicMock(spec=Response)
            mock.status_code = 200
            mock.json.return_value = {"result": []}
            return mock

        with patch("httpx.AsyncClient.post", side_effect=side_effect):
            resp = client.post("/query", json={"query": "totally obscure topic"})
        assert resp.status_code == 404

    def test_query_502_when_llm_fails(self, client):
        def side_effect(*args, **kwargs):
            url = str(args[0]) if args else ""
            if "embeddings" in url:
                return self._make_embedding_response()
            if "search" in url:
                return self._make_vector_search_response()
            mock = MagicMock(spec=Response)
            mock.status_code = 500
            mock.text = "LLM error"
            return mock

        with patch("httpx.AsyncClient.post", side_effect=side_effect):
            resp = client.post("/query", json={"query": "test"})
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Ingest endpoint
# ---------------------------------------------------------------------------

class TestIngestEndpoint:
    def _make_embedding_response(self, count: int = 1):
        mock = MagicMock(spec=Response)
        mock.status_code = 200
        mock.json.return_value = {
            "data": [{"embedding": [0.1] * 1536} for _ in range(count)]
        }
        return mock

    def _make_upsert_response(self):
        mock = MagicMock(spec=Response)
        mock.status_code = 200
        mock.json.return_value = {"status": "ok"}
        return mock

    def test_ingest_returns_202(self, client):
        with patch("httpx.AsyncClient.post", return_value=self._make_embedding_response()):
            with patch("httpx.AsyncClient.put", return_value=self._make_upsert_response()):
                resp = client.post("/ingest", json={"documents": ["Test document."]})
        assert resp.status_code == 202

    def test_ingest_response_schema(self, client):
        with patch("httpx.AsyncClient.post", return_value=self._make_embedding_response()):
            with patch("httpx.AsyncClient.put", return_value=self._make_upsert_response()):
                data = client.post("/ingest", json={"documents": ["Doc 1"]}).json()
        assert "ingested" in data
        assert "failed" in data
        assert "job_id" in data

    def test_ingest_rejects_empty_list(self, client):
        resp = client.post("/ingest", json={"documents": []})
        assert resp.status_code == 422

    def test_ingest_rejects_too_many_docs(self, client):
        resp = client.post("/ingest", json={"documents": ["doc"] * 101})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Security / middleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_request_id_header_present(self, client):
        resp = client.get("/health")
        assert "x-request-id" in resp.headers

    def test_cors_header(self, client):
        resp = client.get("/health", headers={"Origin": "https://example.com"})
        # CORS headers should be present
        assert resp.status_code == 200
