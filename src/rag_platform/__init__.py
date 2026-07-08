"""RAG Platform on Kubernetes.

A production-grade Retrieval-Augmented Generation (RAG) service: document
ingestion, embedding, vector retrieval, and grounded answer generation,
packaged as a FastAPI application and deployed on Kubernetes.

The package is intentionally dependency-light at runtime (standard library +
pydantic + FastAPI) so it is easy to install, test, and reason about. Pluggable
interfaces (``Embedder``, ``VectorStore``) let production deployments swap in
managed model and vector-database backends.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "get_settings",
    "Settings",
    "create_app",
    "RagService",
]

from rag_platform.config import Settings, get_settings
from rag_platform.main import create_app
from rag_platform.service import RagService
