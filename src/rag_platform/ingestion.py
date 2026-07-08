"""Document ingestion: chunking and indexing."""

from __future__ import annotations

import uuid

from rag_platform.embeddings import Embedder
from rag_platform.models import Chunk, Document
from rag_platform.vectorstore import VectorStore


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Split ``text`` into overlapping windows of whitespace-delimited tokens.

    Args:
        text: The source text.
        chunk_size: Maximum number of tokens per chunk.
        overlap: Number of tokens shared between consecutive chunks, which
            preserves context across boundaries.

    Returns:
        A list of chunk strings. An empty or whitespace-only input yields ``[]``.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")

    tokens = text.split()
    if not tokens:
        return []

    step = chunk_size - overlap
    chunks: list[str] = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + chunk_size]
        if window:
            chunks.append(" ".join(window))
        if start + chunk_size >= len(tokens):
            break
    return chunks


class DocumentIngestor:
    """Chunk documents, embed them, and upsert them into a vector store."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def chunk_document(self, document: Document) -> list[Chunk]:
        """Split a single document into :class:`Chunk` objects."""

        doc_id = document.id or str(uuid.uuid4())
        pieces = chunk_text(document.content, self._chunk_size, self._chunk_overlap)
        return [
            Chunk(
                id=f"{doc_id}:{index}",
                document_id=doc_id,
                content=piece,
                metadata={**document.metadata, "chunk_index": index},
            )
            for index, piece in enumerate(pieces)
        ]

    def ingest(self, documents: list[Document]) -> int:
        """Ingest documents, returning the number of chunks written."""

        chunks: list[Chunk] = []
        for document in documents:
            chunks.extend(self.chunk_document(document))
        if not chunks:
            return 0
        vectors = self._embedder.embed([chunk.content for chunk in chunks])
        return self._store.upsert(chunks, vectors)
