"""BM25 (Okapi) implemented from scratch - sparse keyword retrieval.

score(q, d) = sum over query terms t of  IDF(t) * f(t,d)*(k1+1) / (f(t,d) + k1*(1 - b + b*|d|/avgdl))
"""

from __future__ import annotations

import math
from collections import Counter

from .text import tokenize
from .types import Chunk, Hit


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self._chunks: list[Chunk] = []
        self._tf: list[Counter[str]] = []
        self._len: list[int] = []
        self._df: Counter[str] = Counter()
        self._avgdl = 0.0

    def build(self, chunks: list[Chunk]) -> None:
        self._chunks = list(chunks)
        self._tf = [Counter(tokenize(c.text)) for c in chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._df = Counter(t for tf in self._tf for t in tf)
        self._avgdl = (sum(self._len) / len(self._len)) if self._len else 0.0

    def _idf(self, term: str) -> float:
        n, df = len(self._chunks), self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int) -> list[Hit]:
        q_terms = tokenize(query, drop_stopwords=True)
        scored: list[tuple[float, int]] = []
        for i, tf in enumerate(self._tf):
            s = 0.0
            for t in q_terms:
                f = tf.get(t, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self._len[i] / (self._avgdl or 1))
                    s += self._idf(t) * f * (self.k1 + 1) / denom
            if s > 0:
                scored.append((s, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [Hit(self._chunks[i], s, "bm25") for s, i in scored[:k]]

    def __len__(self) -> int:
        return len(self._chunks)
