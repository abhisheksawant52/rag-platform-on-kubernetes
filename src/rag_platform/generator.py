"""Answer generation from retrieved context.

The default :class:`TemplateGenerator` composes a grounded, extractive answer
from the retrieved chunks without calling an external LLM, keeping the package
runnable and testable offline. A production deployment substitutes a generator
that calls the configured chat model (``RAGPLATFORM_LLM_MODEL``) while keeping
the same interface and grounding prompt.
"""

from __future__ import annotations

from rag_platform.models import RetrievedChunk

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question using ONLY the "
    "provided context. If the context does not contain enough information, say "
    "so clearly. Do not invent facts."
)


def build_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks into a numbered context block."""

    return "\n\n".join(
        f"[Source {index + 1}] {chunk.content}" for index, chunk in enumerate(chunks)
    )


class TemplateGenerator:
    """Deterministic, offline answer generator.

    Produces a grounded response by summarising the highest-scoring retrieved
    chunks. Useful as a safe default and for tests; replace with an LLM-backed
    generator in production.
    """

    def __init__(self, model: str = "template-offline", max_sources: int = 3) -> None:
        self.model = model
        self._max_sources = max_sources

    def generate(self, query: str, chunks: list[RetrievedChunk]) -> str:
        """Generate an answer for ``query`` grounded in ``chunks``."""

        if not chunks:
            return "I could not find any relevant context to answer this question."
        top = chunks[: self._max_sources]
        excerpts = " ".join(chunk.content for chunk in top)
        return (
            f"Based on {len(top)} retrieved source(s), here is the grounded answer "
            f'to "{query}": {excerpts}'
        )
