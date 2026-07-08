"""Smoke tests for the operational endpoints of the rag_platform package."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rag_platform.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_returns_200() -> None:
    resp = _client().get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_ready_returns_200() -> None:
    resp = _client().get("/ready")
    assert resp.status_code == 200


def test_query_endpoint_roundtrip() -> None:
    client = _client()
    ingest = client.post(
        "/ingest",
        json={"documents": [{"content": "Kubernetes orchestrates containers at scale."}]},
    )
    assert ingest.status_code == 202

    resp = client.post("/query", json={"query": "Kubernetes orchestrates containers at scale."})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data
    assert "query_id" in data
