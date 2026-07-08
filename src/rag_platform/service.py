"""RagService — orchestrates ingestion, retrieval, and generation."""

from __future__ import annotations

import time
import uuid

from rag_platform.config import Settings, get_settings
from rag_platform.embeddings import Embedder, HashingEmbedder
from rag_platform.generator import TemplateGenerator
from rag_platform.ingestion import DocumentIngestor
from rag_platform.logging_config import get_logger
from rag_platform.models import (
    Document,
    IngestResponse,
    QueryResponse,
)
from rag_platform.retriever import Retriever
from rag_platform.vectorstore import InMemoryVectorStore, VectorStore

logger = get_logger("rag_platform.service")


class RagService:
    """High-level façade tying the RAG pipeline together.

    The constructor accepts pluggable backends so production code can inject a
    real embedder, vector store, and generator. When omitted, dependency-free
    in-memory defaults are used, which keeps the service runnable out of the box.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        generator: TemplateGenerator | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._embedder = embedder or HashingEmbedder(self._settings.embedding_dim)
        self._store = store or InMemoryVectorStore()
        self._generator = generator or TemplateGenerator(model=self._settings.llm_model)
        self._ingestor = DocumentIngestor(
            embedder=self._embedder,
            store=self._store,
            chunk_size=self._settings.chunk_size,
            chunk_overlap=self._settings.chunk_overlap,
        )
        self._retriever = Retriever(
            embedder=self._embedder,
            store=self._store,
            top_k=self._settings.top_k,
        )

    def ingest(self, documents: list[Document]) -> IngestResponse:
        """Chunk, embed, and index ``documents``."""

        job_id = str(uuid.uuid4())
        chunk_count = self._ingestor.ingest(documents)
        logger.info(
            "ingestion complete job_id=%s documents=%d chunks=%d",
            job_id,
            len(documents),
            chunk_count,
        )
        return IngestResponse(
            ingested_documents=len(documents),
            ingested_chunks=chunk_count,
            job_id=job_id,
        )

    def query(self, question: str, top_k: int | None = None) -> QueryResponse:
        """Retrieve relevant context and generate a grounded answer."""

        query_id = str(uuid.uuid4())
        start = time.perf_counter()
        sources = self._retriever.retrieve(question, top_k)
        answer = self._generator.generate(question, sources)
        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "query complete query_id=%s sources=%d latency_ms=%.2f",
            query_id,
            len(sources),
            latency_ms,
        )
        return QueryResponse(
            answer=answer,
            sources=sources,
            query_id=query_id,
            latency_ms=round(latency_ms, 2),
            model=self._generator.model,
        )

    @property
    def document_count(self) -> int:
        """Number of indexed chunks."""

        return self._store.count()
