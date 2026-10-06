# Architecture

## 1. The RAG pipeline (`src/rag/`)

| Stage | Module | Idea |
|---|---|---|
| Load | `loaders.py` | PDF (per page), DOCX, Markdown, TXT -> `Page(source, page, text)`. Markdown headings become standalone sentences. `source` is the bare file name, safe to show to users. |
| Chunk | `chunking.py` | Word windows (120 words, 25 overlap). Overlap keeps facts that straddle a boundary inside one chunk. Chunk IDs are `sha1(source, page, index, text)`, so re-ingesting a document **upserts** rather than duplicates. |
| Embed | `embeddings.py` | `Embedder` protocol. `HashingEmbedder` (offline, deterministic) by default; `SentenceTransformerEmbedder` for real semantic vectors. |
| Dense index | `vector_store.py` | ChromaDB persistent collection, cosine distance. We compute embeddings ourselves. |
| Sparse index | `bm25.py` | Okapi BM25 implemented by hand: `IDF * f(k1+1) / (f + k1(1-b+b*len/avglen))`. |
| Fuse | `hybrid.py` | **RRF**: `score(d) = sum 1/(60 + rank_r(d))`. Needs ranks only, so dense cosine scores and BM25 scores never have to be made comparable. |
| Rerank | `reranker.py` | Rescore the ~20 hybrid candidates and keep the top 4. Cross-encoders read (query, passage) *together*, which is more accurate than comparing two independent vectors. Offline default is an IDF-weighted lexical scorer. |
| Generate | `generator.py` | Prompt: answer only from numbered context, say "I don't know" otherwise, end each sentence with `[n]`. Offline default is an extractive generator (picks and tags the best-matching sentences). Optional Anthropic generator. |
| Verify | `citations.py` | Each sentence must cite a real chunk, and the chunk must support it: >=50% of its content words appear in the chunk and **every number matches**. Failing sentences are dropped and reported. `faithfulness = kept / total`. |
| Orchestrate | `pipeline.py` | `KnowledgeAssistant.ingest / retrieve(mode) / ask`. `version` increments on every data change. |

`retrieve(mode=...)` supports `dense`, `bm25`, `hybrid`, `hybrid_rerank` so the eval can compare stages on identical inputs.

## 2. The service (`src/api/`)

```
client -> [SecurityHeaders] -> [request-id/logging] -> auth dependency (API key + rate limit)
        -> route
           POST /v1/documents -> validate upload -> save -> JobQueue.submit -> 202 {job_id}
                                                              |  worker thread: ka.ingest(), cache.clear()
           POST /v1/ask       -> cache.get((data_version, mode, normalised question))
                                   hit  -> return (cached=true)
                                   miss -> ka.ask() -> cache.set -> return
           GET  /v1/documents, /v1/jobs -> paginate(items, limit<=100, offset)
```

### Caching
`TTLCache`: LRU eviction + per-entry TTL, thread-safe, hit/miss counters exposed at `/v1/stats`. The key includes `ka.version`, and the cache is cleared on ingest/delete, so stale answers are impossible. Question text is normalised (case/whitespace) to raise the hit rate.

### Pagination
`paginate()` clamps `limit` to 1..100 and returns `{items, total, limit, offset, next_offset}`. FastAPI validates the query parameters (422 on bad input).

### Queuing
Ingestion (parse -> chunk -> embed -> index) is slow, so uploads are decoupled from processing: the request validates and saves the file, enqueues a job and returns `202`. A fixed pool of worker threads drains a **bounded** `queue.Queue`. If it is full, the API answers `503` + `Retry-After` instead of accepting unbounded work. A failing job is recorded as `failed` and never kills its worker.

### Concurrency
Ingest and retrieval share one `RLock` around the vector store and BM25 index; BM25 is rebuilt from the store after each change. Simple and correct for a single process.

## 3. Deployment

- **Image**: multi-stage build (wheels built in a throwaway stage), `python:3.12-slim`, unprivileged uid 10001, `HEALTHCHECK` via a stdlib script, `exec` form so uvicorn is PID 1 and handles SIGTERM.
- **Compose**: read-only root FS, `/tmp` tmpfs, `cap_drop: ALL`, `no-new-privileges`, CPU/memory/PID limits, log rotation, a named volume for `/data`, port bound to `127.0.0.1`.
- **CI** (`ci.yml`): lint -> tests on 3 Python versions with an 85% coverage gate -> retrieval-quality gate -> build image, run it with hardened flags, run `scripts/smoke_test.sh`, verify healthy and non-root.
- **Security** (`security.yml`): Bandit, pip-audit, CodeQL, gitleaks, dependency review, Trivy; weekly schedule.
- **CD** (`release.yml`): push a `vX.Y.Z` tag -> verify -> multi-arch image to GHCR with provenance/SBOM/attestation -> GitHub release.

## 4. Known limits and how to scale past them

| Limit | Fix |
|---|---|
| Cache, rate limiter and job state are per process | Redis for cache + rate limits; Celery/RQ + Redis for jobs. The interfaces (`get/set/clear`, `submit/get/list`) are already minimal |
| Embedded Chroma on a local volume (one writer) | Run Chroma as a server, or move to a managed vector DB (pgvector, OpenSearch) |
| BM25 is rebuilt in memory on every change and loaded entirely in RAM | Fine for thousands of chunks. For millions, use OpenSearch/Elasticsearch for the sparse side |
| Offset pagination degrades on huge lists | Switch to keyset/cursor pagination |
| No document-level permissions | Add tenant/ACL metadata on chunks and filter at retrieval |
| Faithfulness check is lexical | Add an NLI / LLM-judge verifier behind the same `verify()` interface |
