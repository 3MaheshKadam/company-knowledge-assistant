"""Embedding backends behind one interface.

* HashingEmbedder - offline, deterministic, zero downloads (default; used in CI/tests).
* SentenceTransformerEmbedder - real neural embeddings (`pip install .[ml]`).
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from .text import tokenize


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Signed feature-hashing of unigrams + bigrams into a fixed vector, L2-normalised.

    Not semantic like a neural model, but captures lexical overlap and is fully reproducible.
    """

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        toks = tokenize(text, drop_stopwords=True)
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        v = [0.0] * self.dim
        for f in feats:
            h = int.from_bytes(hashlib.md5(f.encode(), usedforsecurity=False).digest()[:8], "big")
            v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class SentenceTransformerEmbedder:
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer

        self._m = SentenceTransformer(model)
        self.dim = int(self._m.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._m.encode(texts, normalize_embeddings=True).tolist()


def get_embedder(name: str) -> Embedder:
    if name == "hashing":
        return HashingEmbedder()
    if name == "sentence-transformers":
        return SentenceTransformerEmbedder()
    raise ValueError(f"Unknown embedder: {name}")
