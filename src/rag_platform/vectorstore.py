"""Vector store backends.

The :class:`VectorStore` protocol mirrors the small surface the platform needs:
upsert chunk vectors and search by nearest neighbour. :class:`InMemoryVectorStore`
is a brute-force cosine implementation used for local development and tests; a
production deployment points at Qdrant (see ``RAGPLATFORM_VECTOR_STORE_URL``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_platform.embeddings import Vector, cosine_similarity
from rag_platform.models import Chunk, RetrievedChunk


@runtime_checkable
class VectorStore(Protocol):
    """Minimal vector-store contract."""

    def upsert(self, chunks: list[Chunk], vectors: list[Vector]) -> int:
        """Insert or update chunk vectors; return the count written."""
        ...

    def search(self, query_vector: Vector, top_k: int) -> list[RetrievedChunk]:
        """Return the ``top_k`` most similar chunks, highest score first."""
        ...

    def count(self) -> int:
        """Return the number of stored chunks."""
        ...


class InMemoryVectorStore:
    """Brute-force cosine-similarity store backed by a Python dict."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, Vector] = {}

    def upsert(self, chunks: list[Chunk], vectors: list[Vector]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must be the same length")
        for chunk, vector in zip(chunks, vectors):
            self._chunks[chunk.id] = chunk
            self._vectors[chunk.id] = vector
        return len(chunks)

    def search(self, query_vector: Vector, top_k: int) -> list[RetrievedChunk]:
        scored = [
            RetrievedChunk(
                id=chunk_id,
                content=self._chunks[chunk_id].content,
                score=cosine_similarity(query_vector, vector),
                metadata=self._chunks[chunk_id].metadata,
            )
            for chunk_id, vector in self._vectors.items()
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(top_k, 0)]

    def count(self) -> int:
        return len(self._chunks)
