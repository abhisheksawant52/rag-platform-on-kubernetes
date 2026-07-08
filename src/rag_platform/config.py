"""Runtime configuration.

All settings are read from environment variables prefixed with ``RAGPLATFORM_``
(twelve-factor style). For example, ``RAGPLATFORM_TOP_K=8`` overrides
:attr:`Settings.top_k`. Values may also be supplied via a local ``.env`` file
(see ``.env.example``).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Attributes map 1:1 to ``RAGPLATFORM_*`` environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="RAGPLATFORM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "rag-platform"
    environment: str = "production"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Vector store ---
    vector_store_url: str = "http://qdrant:6333"
    collection_name: str = "rag_documents"

    # --- Models ---
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 384
    llm_model: str = "gpt-4o-mini"

    # --- Retrieval / chunking ---
    top_k: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 64
    max_tokens: int = 1024
    temperature: float = 0.2

    # --- Security ---
    allowed_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Cached so configuration is parsed from the environment exactly once per
    process. Call ``get_settings.cache_clear()`` in tests to force a reload.
    """

    return Settings()
