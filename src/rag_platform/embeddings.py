"""Text embedding backends.

The :class:`Embedder` protocol defines the contract used by the ingestion and
retrieval paths. :class:`HashingEmbedder` is a deterministic, dependency-free
default suitable for local development and tests. In production you would swap
in a real model client (for example ``sentence-transformers`` or the OpenAI
embeddings API) that satisfies the same protocol.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

Vector = list[float]


@runtime_checkable
class Embedder(Protocol):
    """Anything that can turn text into fixed-length vectors."""

    dimension: int

    def embed(self, texts: list[str]) -> list[Vector]:
        """Embed a batch of texts into unit-length vectors."""
        ...


class HashingEmbedder:
    """Deterministic hashing embedder.

    Uses the "hashing trick": each token is hashed into a bucket and its
    signed contribution accumulated, then the vector is L2-normalised. This is
    not semantic, but it is fast, deterministic, and requires no model
    download, which makes it ideal for tests and offline development.
    """

    def __init__(self, dimension: int = 384) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def _embed_one(self, text: str) -> Vector:
        vec = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(component * component for component in vec))
        if norm == 0.0:
            return vec
        return [component / norm for component in vec]

    def embed(self, texts: list[str]) -> list[Vector]:
        """Embed a batch of texts."""

        return [self._embed_one(text) for text in texts]


def cosine_similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity between two equal-length vectors."""

    if len(a) != len(b):
        raise ValueError("vectors must have the same dimension")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
