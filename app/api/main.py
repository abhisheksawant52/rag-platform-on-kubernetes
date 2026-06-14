"""
RAG Platform FastAPI Application
Production-ready implementation with health checks, metrics, structured logging,
input validation, error handling, and OpenAI/vector-store integration.
"""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


# ---------------------------------------------------------------------------
# Settings (all values come from environment variables / Kubernetes Secrets)
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    app_name: str = "rag-platform"
    app_version: str = "1.0.0"
    environment: str = "production"
    log_level: str = "INFO"

    # OpenAI / LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Vector store
    vector_store_url: str = "http://qdrant:6333"
    collection_name: str = "rag_documents"

    # Retrieval
    top_k: int = 5
    max_tokens: int = 1024
    temperature: float = 0.2

    # Observability
    otlp_endpoint: str = ""

    # Security
    allowed_origins: list[str] = ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(settings.app_name)


# ---------------------------------------------------------------------------
# OpenTelemetry tracing (optional — only configured when OTLP endpoint set)
# ---------------------------------------------------------------------------

def configure_tracing() -> None:
    if not settings.otlp_endpoint:
        return
    resource = Resource(attributes={"service.name": settings.app_name, "deployment.environment": settings.environment})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)))
    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry tracing configured", extra={"endpoint": settings.otlp_endpoint})


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "rag_request_total",
    "Total number of requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "rag_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
ACTIVE_REQUESTS = Gauge("rag_active_requests", "Currently active requests")
RETRIEVAL_LATENCY = Histogram(
    "rag_retrieval_duration_seconds",
    "Vector retrieval latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)
LLM_LATENCY = Histogram(
    "rag_llm_duration_seconds",
    "LLM generation latency",
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)
RETRIEVAL_DOCS = Histogram(
    "rag_retrieved_docs_count",
    "Number of documents retrieved per query",
    buckets=[1, 2, 3, 5, 10],
)


# ---------------------------------------------------------------------------
# Middleware — request ID + metrics
# ---------------------------------------------------------------------------

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        ACTIVE_REQUESTS.inc()
        try:
            response = await call_next(request)
            duration = time.perf_counter() - start
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
            ).inc()
            REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=500).inc()
            raise exc
        finally:
            ACTIVE_REQUESTS.dec()


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_tracing()
    logger.info("Starting %s v%s [%s]", settings.app_name, settings.app_version, settings.environment)
    # Validate critical dependencies are reachable on startup
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.vector_store_url}/healthz")
            if resp.status_code >= 400:
                logger.warning("Vector store health check returned %s", resp.status_code)
    except Exception as exc:
        logger.warning("Could not reach vector store at startup: %s", exc)
    yield
    logger.info("Shutting down %s", settings.app_name)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RAG Platform API",
    version=settings.app_version,
    description="Production-grade Retrieval-Augmented Generation platform on Kubernetes",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

FastAPIInstrumentor.instrument_app(app)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048, description="User query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents to retrieve")
    conversation_id: str | None = Field(default=None, description="Optional conversation tracking ID")


class DocumentSource(BaseModel):
    id: str
    score: float
    content: str
    metadata: dict[str, Any] = {}


class QueryResponse(BaseModel):
    answer: str
    sources: list[DocumentSource]
    query_id: str
    latency_ms: float
    model: str


class IngestRequest(BaseModel):
    documents: list[str] = Field(..., min_items=1, max_items=100, description="Documents to ingest")
    metadata: list[dict[str, Any]] = Field(default_factory=list)


class IngestResponse(BaseModel):
    ingested: int
    failed: int
    job_id: str


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    dependencies: dict[str, str]


# ---------------------------------------------------------------------------
# RAG service helpers
# ---------------------------------------------------------------------------

async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API."""
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="LLM service not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"input": texts, "model": settings.embedding_model},
        )
        if resp.status_code != 200:
            logger.error("Embeddings API error: %s %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail="Embedding service error")
        data = resp.json()
        return [item["embedding"] for item in data["data"]]


async def retrieve_documents(query_embedding: list[float], top_k: int) -> list[DocumentSource]:
    """Query vector store for nearest neighbours."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.vector_store_url}/collections/{settings.collection_name}/points/search",
            json={"vector": query_embedding, "limit": top_k, "with_payload": True},
        )
        if resp.status_code != 200:
            logger.error("Vector store error: %s %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail="Vector store error")
        results = resp.json().get("result", [])
        return [
            DocumentSource(
                id=str(r["id"]),
                score=r["score"],
                content=r.get("payload", {}).get("content", ""),
                metadata=r.get("payload", {}).get("metadata", {}),
            )
            for r in results
        ]


async def generate_answer(query: str, context_docs: list[DocumentSource]) -> str:
    """Call LLM to generate grounded answer from retrieved context."""
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="LLM service not configured")
    context = "\n\n".join(
        f"[Source {i+1}] {doc.content}" for i, doc in enumerate(context_docs)
    )
    system_prompt = (
        "You are a helpful assistant. Answer the user's question using ONLY the provided context. "
        "If the context does not contain enough information, say so clearly. "
        "Do not hallucinate or invent facts."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
    ]
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "messages": messages,
                "max_tokens": settings.max_tokens,
                "temperature": settings.temperature,
            },
        )
        if resp.status_code != 200:
            logger.error("LLM API error: %s %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail="LLM service error")
        return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health():
    """Liveness probe — always returns 200 if the process is up."""
    vector_store_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.vector_store_url}/healthz")
            vector_store_status = "healthy" if r.status_code < 400 else "degraded"
    except Exception:
        vector_store_status = "unreachable"

    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.environment,
        dependencies={"vector_store": vector_store_status},
    )


@app.get("/readyz", tags=["ops"])
async def readiness():
    """Readiness probe — returns 503 when critical deps are unavailable."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.vector_store_url}/healthz")
            if r.status_code >= 400:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector store degraded")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"status": "ready"}


@app.get("/metrics", tags=["ops"], include_in_schema=False)
async def metrics():
    """Prometheus metrics scrape endpoint."""
    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")


@app.post("/query", response_model=QueryResponse, tags=["rag"])
async def query(request: QueryRequest):
    """
    Submit a RAG query. The API will:
    1. Embed the query
    2. Retrieve top-k relevant documents from the vector store
    3. Generate a grounded answer via LLM
    """
    query_id = str(uuid.uuid4())
    start = time.perf_counter()

    logger.info("Processing query", extra={"query_id": query_id, "query_length": len(request.query)})

    # Embed
    with RETRIEVAL_LATENCY.time():
        embeddings = await get_embeddings([request.query])
        docs = await retrieve_documents(embeddings[0], request.top_k)

    RETRIEVAL_DOCS.observe(len(docs))

    if not docs:
        raise HTTPException(status_code=404, detail="No relevant documents found for the query")

    # Generate
    with LLM_LATENCY.time():
        answer = await generate_answer(request.query, docs)

    latency_ms = (time.perf_counter() - start) * 1000
    logger.info("Query complete", extra={"query_id": query_id, "latency_ms": latency_ms, "docs_retrieved": len(docs)})

    return QueryResponse(
        answer=answer,
        sources=docs,
        query_id=query_id,
        latency_ms=round(latency_ms, 2),
        model=settings.openai_model,
    )


@app.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED, tags=["rag"])
async def ingest(request: IngestRequest):
    """
    Ingest documents into the vector store.
    Embeds all documents and upserts them into the configured collection.
    """
    job_id = str(uuid.uuid4())
    failed = 0
    ingested = 0

    logger.info("Starting ingestion job", extra={"job_id": job_id, "doc_count": len(request.documents)})

    try:
        embeddings = await get_embeddings(request.documents)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Embedding failed for job %s", job_id)
        raise HTTPException(status_code=502, detail="Failed to embed documents") from exc

    points = []
    for i, (doc, emb) in enumerate(zip(request.documents, embeddings)):
        meta = request.metadata[i] if i < len(request.metadata) else {}
        points.append({
            "id": str(uuid.uuid4()),
            "vector": emb,
            "payload": {"content": doc, "metadata": meta},
        })

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{settings.vector_store_url}/collections/{settings.collection_name}/points",
            json={"points": points},
        )
        if resp.status_code != 200:
            logger.error("Vector upsert failed: %s", resp.text)
            failed = len(points)
        else:
            ingested = len(points)

    logger.info("Ingestion job complete", extra={"job_id": job_id, "ingested": ingested, "failed": failed})
    return IngestResponse(ingested=ingested, failed=failed, job_id=job_id)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": getattr(request.state, "request_id", None)},
    )
