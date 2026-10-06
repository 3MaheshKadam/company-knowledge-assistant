"""ChromaDB wrapper (persistent, cosine distance). Embeddings are computed by us, not by Chroma."""

from __future__ import annotations

from pathlib import Path

import chromadb

from .types import Chunk, Hit


class VectorStore:
    def __init__(self, path: Path | str, collection: str = "company_docs") -> None:
        self._client = chromadb.PersistentClient(
            path=str(path),
            settings=chromadb.Settings(anonymized_telemetry=False),  # no outbound calls from a locked-down container
        )
        self._col = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        self._col.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,  # type: ignore[arg-type]
            metadatas=[{"source": c.source, "page": c.page, "index": c.index} for c in chunks],
        )

    def query(self, embedding: list[float], k: int) -> list[Hit]:
        n = self._col.count()
        if n == 0:
            return []
        res = self._col.query(query_embeddings=[embedding], n_results=min(k, n))  # type: ignore[arg-type]
        hits = []
        for cid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True  # type: ignore[index]
        ):
            chunk = Chunk(cid, doc, str(meta["source"]), int(meta["page"]), int(meta["index"]))  # type: ignore[arg-type]
            hits.append(Hit(chunk, 1.0 - float(dist), "dense"))
        return hits

    def all_chunks(self) -> list[Chunk]:
        res = self._col.get(include=["documents", "metadatas"])
        out = [
            Chunk(cid, doc, str(m["source"]), int(m["page"]), int(m["index"]))  # type: ignore[arg-type]
            for cid, doc, m in zip(res["ids"], res["documents"], res["metadatas"], strict=True)  # type: ignore[arg-type]
        ]
        out.sort(key=lambda c: (c.source, c.page, c.index))
        return out

    def delete_source(self, source: str) -> int:
        res = self._col.get(where={"source": source})
        ids = res["ids"]
        if ids:
            self._col.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        return self._col.count()
