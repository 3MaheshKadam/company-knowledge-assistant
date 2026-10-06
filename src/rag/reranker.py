"""Second-stage reranking of the hybrid candidates.

* LexicalReranker - offline: IDF-weighted query-term coverage + phrase bonus (default).
* CrossEncoderReranker - neural cross-encoder (`pip install .[ml]`), scores (query, passage) jointly.
"""

from __future__ import annotations

import math
from typing import Protocol

from .text import tokenize
from .types import Hit


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[Hit], top_k: int) -> list[Hit]: ...


class LexicalReranker:
    def rerank(self, query: str, hits: list[Hit], top_k: int) -> list[Hit]:
        q = tokenize(query, drop_stopwords=True)
        if not hits or not q:
            return hits[:top_k]
        docs = [set(tokenize(h.chunk.text)) for h in hits]
        n = len(docs)
        df = {t: sum(t in d for d in docs) for t in set(q)}
        idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in df}
        total = sum(idf.values()) or 1.0
        q_bigrams = {f"{a} {b}" for a, b in zip(q, q[1:], strict=False)}
        scored = []
        for h, d in zip(hits, docs, strict=True):
            coverage = sum(idf[t] for t in set(q) if t in d) / total
            text = " ".join(tokenize(h.chunk.text, drop_stopwords=True))
            phrase = sum(bg in text for bg in q_bigrams) / (len(q_bigrams) or 1)
            scored.append(Hit(h.chunk, 0.8 * coverage + 0.2 * phrase, "rerank"))
        scored.sort(key=lambda x: (-x.score, x.chunk.id))
        return scored[:top_k]


class CrossEncoderReranker:
    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        from sentence_transformers import CrossEncoder

        self._m = CrossEncoder(model)

    def rerank(self, query: str, hits: list[Hit], top_k: int) -> list[Hit]:
        if not hits:
            return []
        scores = self._m.predict([(query, h.chunk.text) for h in hits])
        ranked = sorted(zip(hits, scores, strict=True), key=lambda x: -float(x[1]))
        return [Hit(h.chunk, float(s), "rerank") for h, s in ranked[:top_k]]


def get_reranker(name: str) -> Reranker:
    if name == "lexical":
        return LexicalReranker()
    if name == "cross-encoder":
        return CrossEncoderReranker()
    raise ValueError(f"Unknown reranker: {name}")
