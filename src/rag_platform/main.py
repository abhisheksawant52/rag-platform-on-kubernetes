"""FastAPI application factory and HTTP routes.

Exposes the operational endpoints expected by the Kubernetes manifests
(``/health`` liveness, ``/ready`` readiness — also aliased as ``/readyz`` to
match the Helm probe paths) and the RAG endpoints ``/query`` and ``/ingest``.
The container listens on port 8000 (see the Dockerfile and helm/values.yaml).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rag_platform import __version__
from rag_platform.config import Settings, get_settings
from rag_platform.logging_config import configure_logging
from rag_platform.models import (
    HealthStatus,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from rag_platform.service import RagService


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    Args:
        settings: Optional settings override (useful in tests). Defaults to the
            cached process settings from :func:`get_settings`.
    """

    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="RAG Platform API",
        version=__version__,
        description="Production-grade Retrieval-Augmented Generation platform on Kubernetes",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    service = RagService(settings=settings)
    app.state.settings = settings
    app.state.service = service

    def _health() -> HealthStatus:
        return HealthStatus(
            status="ok",
            version=__version__,
            environment=settings.environment,
            dependencies={"vector_store": "in-memory"},
        )

    @app.get("/health", response_model=HealthStatus, tags=["ops"])
    def health() -> HealthStatus:
        """Liveness probe — returns 200 whenever the process is serving."""

        return _health()

    @app.get("/ready", response_model=HealthStatus, tags=["ops"])
    def ready() -> HealthStatus:
        """Readiness probe — the service is ready once dependencies are wired."""

        return _health()

    @app.get("/readyz", response_model=HealthStatus, tags=["ops"], include_in_schema=False)
    def readyz() -> HealthStatus:
        """Alias of ``/ready`` matching the Helm/Kustomize probe path."""

        return _health()

    @app.post("/query", response_model=QueryResponse, tags=["rag"])
    def query(request: QueryRequest) -> QueryResponse:
        """Run a RAG query: retrieve relevant chunks and generate an answer."""

        return service.query(request.query, request.top_k)

    @app.post("/ingest", response_model=IngestResponse, status_code=202, tags=["rag"])
    def ingest(request: IngestRequest) -> IngestResponse:
        """Ingest documents into the vector index."""

        return service.ingest(request.documents)

    return app


app = create_app()
