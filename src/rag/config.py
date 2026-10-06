"""Central configuration, read from environment variables (12-factor style).

Every field uses a default_factory so the environment is read when `Settings()` is created,
not at import time - this keeps tests hermetic and lets containers configure everything via env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _s(name: str, default: str) -> str:
    return field(default_factory=lambda: os.environ.get(name, default))  # type: ignore[return-value]


def _i(name: str, default: int) -> int:
    return field(default_factory=lambda: int(os.environ.get(name, default)))  # type: ignore[return-value]


def _f(name: str, default: float) -> float:
    return field(default_factory=lambda: float(os.environ.get(name, default)))  # type: ignore[return-value]


def _b(name: str, default: bool) -> bool:
    return field(default_factory=lambda: os.environ.get(name, str(default)).lower() == "true")  # type: ignore[return-value]


def _csv(name: str) -> tuple[str, ...]:
    return field(  # type: ignore[return-value]
        default_factory=lambda: tuple(x.strip() for x in os.environ.get(name, "").split(",") if x.strip())
    )


def _p(name: str, default: str) -> Path:
    return field(default_factory=lambda: Path(os.environ.get(name, default)))  # type: ignore[return-value]


@dataclass(frozen=True)
class Settings:
    # storage
    chroma_dir: Path = _p("RAG_CHROMA_DIR", "chroma_db")
    upload_dir: Path = _p("RAG_UPLOAD_DIR", "data/uploads")
    collection: str = _s("RAG_COLLECTION", "company_docs")
    # chunking (in words)
    chunk_size: int = _i("RAG_CHUNK_SIZE", 120)
    chunk_overlap: int = _i("RAG_CHUNK_OVERLAP", 25)
    # retrieval
    candidates_k: int = _i("RAG_CANDIDATES_K", 20)
    final_k: int = _i("RAG_FINAL_K", 4)
    rrf_k: int = _i("RAG_RRF_K", 60)
    # backends: "hashing"|"sentence-transformers", "lexical"|"cross-encoder", "extractive"|"anthropic"
    embedder: str = _s("RAG_EMBEDDER", "hashing")
    reranker: str = _s("RAG_RERANKER", "lexical")
    generator: str = _s("RAG_GENERATOR", "extractive")
    llm_model: str = _s("RAG_LLM_MODEL", "claude-sonnet-5-5")
    # grounding
    min_support: float = _f("RAG_MIN_SUPPORT", 0.5)
    # api / security
    api_keys: tuple[str, ...] = _csv("RAG_API_KEYS")
    allow_anonymous: bool = _b("RAG_ALLOW_ANONYMOUS", False)
    max_upload_mb: int = _i("RAG_MAX_UPLOAD_MB", 10)
    rate_limit_per_min: int = _i("RAG_RATE_LIMIT_PER_MIN", 60)
    cors_origins: tuple[str, ...] = _csv("RAG_CORS_ORIGINS")
    # caching / queue
    cache_ttl_s: int = _i("RAG_CACHE_TTL_S", 300)
    cache_max_items: int = _i("RAG_CACHE_MAX_ITEMS", 512)
    queue_workers: int = _i("RAG_QUEUE_WORKERS", 2)
    queue_max_size: int = _i("RAG_QUEUE_MAX_SIZE", 100)


def get_settings() -> Settings:
    return Settings()
