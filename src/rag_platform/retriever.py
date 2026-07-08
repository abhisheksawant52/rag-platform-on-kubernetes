"""Retrieval: embed a query and fetch the most relevant chunks."""

from __future__ import annotations

from rag_platform.embeddings import Embedder
from rag_platform.models import RetrievedChunk
from rag_platform.vectorstore import VectorStore


class Retriever:
    """Embed queries and rank chunks from the vector store by similarity."""

    def __init__(self, embedder: Embedder, store: VectorStore, top_k: int = 5) -> None:
        self._embedder = embedder
        self._store = store
        self._top_k = top_k

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Return chunks most relevant to ``query``, highest score first."""

        k = top_k if top_k is not None else self._top_k
        query_vector = self._embedder.embed([query])[0]
        return self._store.search(query_vector, k)
