"""Pydantic data models shared across the RAG pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A raw source document supplied for ingestion."""

    id: str | None = Field(default=None, description="Optional caller-supplied identifier")
    content: str = Field(..., min_length=1, description="Full document text")
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """A contiguous slice of a document, the unit stored in the vector index."""

    id: str
    document_id: str | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    """A chunk returned from vector search with its similarity score."""

    id: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryRequest(BaseModel):
    """Request body for ``POST /query``."""

    query: str = Field(..., min_length=1, max_length=2048, description="User question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of chunks to retrieve")


class QueryResponse(BaseModel):
    """Response body for ``POST /query``."""

    answer: str
    sources: list[RetrievedChunk]
    query_id: str
    latency_ms: float
    model: str


class IngestRequest(BaseModel):
    """Request body for ``POST /ingest``."""

    documents: list[Document] = Field(..., min_length=1, max_length=100)


class IngestResponse(BaseModel):
    """Response body for ``POST /ingest``."""

    ingested_documents: int
    ingested_chunks: int
    job_id: str


class HealthStatus(BaseModel):
    """Response body for ``/health`` and ``/ready``."""

    status: str
    version: str
    environment: str
    dependencies: dict[str, str] = Field(default_factory=dict)
