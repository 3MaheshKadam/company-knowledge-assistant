"""Reciprocal Rank Fusion: merge ranked lists without needing comparable scores.

RRF(d) = sum over rankers r of 1 / (k + rank_r(d)),  rank starting at 1.
"""

from __future__ import annotations

from .types import Chunk, Hit


def rrf_fuse(rankings: list[list[Hit]], k: int = 60, top_n: int | None = None) -> list[Hit]:
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + 1.0 / (k + rank)
            chunks[hit.chunk.id] = hit.chunk
    fused = sorted(scores, key=lambda cid: (-scores[cid], cid))
    hits = [Hit(chunks[cid], scores[cid], "hybrid") for cid in fused]
    return hits[:top_n] if top_n else hits
