"""Unit tests for chunking and retrieval ranking."""

from __future__ import annotations

from rag_platform.embeddings import HashingEmbedder
from rag_platform.ingestion import chunk_text
from rag_platform.models import Document
from rag_platform.service import RagService
from rag_platform.vectorstore import InMemoryVectorStore


def test_chunk_text_respects_size_and_overlap() -> None:
    tokens = [f"w{i}" for i in range(250)]
    text = " ".join(tokens)
    chunks = chunk_text(text, chunk_size=100, overlap=20)

    # step = 80 -> starts at 0, 80, 160, 240 => 4 chunks
    assert len(chunks) == 4
    # Each chunk (except possibly the last) has exactly chunk_size tokens.
    assert len(chunks[0].split()) == 100
    # Overlap: last 20 tokens of chunk 0 equal first 20 tokens of chunk 1.
    first = chunks[0].split()
    second = chunks[1].split()
    assert first[-20:] == second[:20]


def test_chunk_text_empty_input() -> None:
    assert chunk_text("   ", chunk_size=10, overlap=2) == []


def test_retrieval_ranks_exact_match_first() -> None:
    embedder = HashingEmbedder(dimension=128)
    store = InMemoryVectorStore()
    service = RagService(embedder=embedder, store=store)

    service.ingest(
        [
            Document(id="a", content="the capital of france is paris"),
            Document(id="b", content="python is a programming language"),
            Document(id="c", content="mount everest is the tallest mountain"),
        ]
    )

    response = service.query("the capital of france is paris", top_k=3)
    assert response.sources, "expected at least one retrieved source"
    # The identical document should have the highest similarity score.
    assert "paris" in response.sources[0].content
    scores = [s.score for s in response.sources]
    assert scores == sorted(scores, reverse=True)
