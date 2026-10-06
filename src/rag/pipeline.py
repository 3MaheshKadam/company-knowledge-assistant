"""KnowledgeAssistant: wires loaders -> chunking -> embeddings -> Chroma + BM25 -> RRF -> rerank
-> generation -> citation verification."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from .bm25 import BM25Index
from .chunking import chunk_pages
from .citations import build_answer
from .config import Settings, get_settings
from .embeddings import get_embedder
from .generator import get_generator
from .hybrid import rrf_fuse
from .loaders import load_document
from .reranker import get_reranker
from .types import Answer, Hit
from .vector_store import VectorStore

MODES = ("dense", "bm25", "hybrid", "hybrid_rerank")


@dataclass
class IngestResult:
    source: str
    pages: int
    chunks: int


class KnowledgeAssistant:
    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self.embedder = get_embedder(self.s.embedder)
        self.store = VectorStore(self.s.chroma_dir, self.s.collection)
        self.bm25 = BM25Index()
        self.reranker = get_reranker(self.s.reranker)
        self.generator = get_generator(self.s.generator, self.s.llm_model)
        self._lock = threading.RLock()
        self.version = 0  # bumped on every data change; the API cache keys on it
        self.bm25.build(self.store.all_chunks())

    # ---- ingestion -------------------------------------------------------------------------
    def ingest(self, path: str | Path) -> IngestResult:
        pages = load_document(path)
        chunks = chunk_pages(pages, self.s.chunk_size, self.s.chunk_overlap)
        embeddings = self.embedder.embed([c.text for c in chunks]) if chunks else []
        with self._lock:
            self.store.upsert(chunks, embeddings)
            self.bm25.build(self.store.all_chunks())
            self.version += 1
        return IngestResult(Path(path).name, len(pages), len(chunks))

    def delete(self, source: str) -> int:
        with self._lock:
            n = self.store.delete_source(source)
            self.bm25.build(self.store.all_chunks())
            self.version += 1
        return n

    def documents(self) -> list[dict[str, object]]:
        counts: dict[str, int] = {}
        for c in self.store.all_chunks():
            counts[c.source] = counts.get(c.source, 0) + 1
        return [{"source": s, "chunks": n} for s, n in sorted(counts.items())]

    # ---- retrieval -------------------------------------------------------------------------
    def retrieve(self, question: str, mode: str = "hybrid_rerank", k: int | None = None) -> list[Hit]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        k = k or self.s.final_k
        pool = max(self.s.candidates_k, k)
        with self._lock:
            if mode == "bm25":
                return self.bm25.search(question, k)
            dense = self.store.query(self.embedder.embed([question])[0], pool)
            if mode == "dense":
                return dense[:k]
            fused = rrf_fuse([dense, self.bm25.search(question, pool)], self.s.rrf_k)
        if mode == "hybrid":
            return fused[:k]
        return self.reranker.rerank(question, fused[:pool], k)

    # ---- answering -------------------------------------------------------------------------
    def ask(self, question: str, mode: str = "hybrid_rerank") -> Answer:
        hits = self.retrieve(question, mode)
        raw = self.generator.generate(question, hits)
        return build_answer(question, raw, hits, self.s.min_support)
