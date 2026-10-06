"""Word-window chunking with overlap, so facts split across a boundary survive in one chunk."""

from __future__ import annotations

import hashlib

from .types import Chunk, Page


def chunk_page(page: Page, size: int = 120, overlap: int = 25) -> list[Chunk]:
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and < size")
    words = page.text.split()
    step = size - overlap
    chunks: list[Chunk] = []
    for idx, start in enumerate(range(0, max(len(words), 1), step)):
        window = words[start : start + size]
        if not window:
            break
        text = " ".join(window)
        # Deterministic id => re-ingesting the same document upserts instead of duplicating.
        cid = hashlib.sha1(f"{page.source}|{page.page}|{idx}|{text}".encode(), usedforsecurity=False).hexdigest()[:16]
        chunks.append(Chunk(cid, text, page.source, page.page, idx))
        if start + size >= len(words):
            break
    return chunks


def chunk_pages(pages: list[Page], size: int = 120, overlap: int = 25) -> list[Chunk]:
    out: list[Chunk] = []
    for p in pages:
        out.extend(chunk_page(p, size, overlap))
    return out
