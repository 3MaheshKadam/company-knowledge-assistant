# Company Knowledge Assistant

A **from-scratch RAG system** that answers questions about company documents (HR policies, handbooks, SOPs, runbooks) and **proves where every answer came from**. It is built component by component, with no LangChain black box, then wrapped in a production-style service: FastAPI, Docker, CI/CD, auth, caching, pagination and a job queue.

```
 DOCUMENTS (PDF / DOCX / MD / TXT)
        │  loaders.py
        ▼
     CHUNKING  (overlapping word windows, deterministic IDs)
        │
   ┌────┴─────────────┐
   ▼                  ▼
EMBEDDINGS         BM25 INDEX            <- written from scratch
   │                  │
   ▼                  ▼
CHROMADB          SPARSE SEARCH
   └────────┬─────────┘
            ▼
     HYBRID SEARCH + RRF                 <- Reciprocal Rank Fusion
            ▼
        RERANKING                        <- cross-encoder (or offline lexical)
            ▼
       LLM / GENERATOR                   <- strict "answer only from context" prompt
            ▼
   CITATION VERIFICATION                 <- drops claims the cited chunk doesn't support
            ▼
  GROUNDED ANSWER + CITATIONS
```

## Results

Measured on the bundled synthetic corpus (5 documents, 22 answerable + 3 unanswerable questions, k=4). Reproduce with `python -m eval.run_eval`.

| Retriever | Recall@4 | MRR | Latency (ms) |
|---|---|---|---|
| Dense (Chroma) | 0.95 | 0.89 | 2.9 |
| BM25 | 0.95 | 0.95 | <0.1 |
| Hybrid (RRF) | 0.95 | 0.93 | 3.4 |
| Hybrid + Rerank | 0.95 | 0.95 | 4.1 |

| End-to-end metric | Score |
|---|---|
| Answer accuracy | 0.95 |
| Citation precision | 0.95 |
| Faithfulness (claims passing citation check) | 1.00 |
| Abstention on unanswerable questions ("I don't know") | 1.00 |

**Read these numbers honestly.** The test set is small and the documents are clean, so every retriever saturates near 0.95 and the differences between them are within noise. The one miss is instructive: *"What is the minimum password length?"* vs the document's *"Passwords must be at least 14 characters long"*. There is no shared vocabulary, which is a case where neural embeddings (`pip install .[ml]`) should help. The default offline backends (hashing embedder, lexical reranker, extractive generator) exist so CI and the eval run with no downloads and no API key. The code paths for the neural embedder, cross-encoder and LLM generator are implemented but are **not** exercised by the test suite. Growing the eval set and running it with those backends is the natural next step.

## Features

| Area | What's implemented |
|---|---|
| **Retrieval** | Chroma dense search, BM25 (from scratch), hybrid fusion with RRF, second-stage reranking |
| **Grounding** | Strict prompt; every sentence must carry a `[n]` citation; **verifier checks the cited chunk supports the sentence** (word overlap and exact number match) and drops what it doesn't |
| **Pluggable backends** | Embedder, reranker and generator are swappable by env var (`hashing` / `sentence-transformers`, `lexical` / `cross-encoder`, `extractive` / `anthropic`) |
| **Security** | API-key auth (constant-time compare, secure by default), per-client rate limiting, upload allow-list + magic-byte check + size cap + filename sanitising, security headers, CORS allow-list, non-root read-only container |
| **Caching** | Thread-safe LRU+TTL cache for answers, keyed by data version, so it never serves stale answers after an upload or delete |
| **Pagination** | Bounded offset pagination (`limit` ≤ 100) on list endpoints |
| **Queuing** | Uploads return `202` and a job ID; a bounded worker queue ingests in the background. A full queue gives `503` + `Retry-After` (backpressure) |
| **DevOps** | Multi-stage Dockerfile, hardened docker-compose, GitHub Actions CI (lint, tests on py3.10-3.12 with a coverage gate, eval quality gate, container smoke test), security workflow (Bandit, pip-audit, CodeQL, gitleaks, Trivy, dependency review), tag-driven release to GHCR with provenance and SBOM, Dependabot |

## Quick start

### Docker (recommended)

```bash
cp .env.example .env            # set RAG_API_KEYS to a long random value
docker compose up --build -d
docker compose --profile seed run --rm seed     # load the sample documents
curl -s -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"question":"How many days of annual leave do full-time employees get?"}' \
  http://localhost:8000/v1/ask
```

Interactive docs: `http://localhost:8000/docs`.

### Local

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
make test            # pytest with coverage
make eval            # retrieval + end-to-end evaluation table
make run             # dev server on :8000 (anonymous mode, dev only)
```

### Use it as a library

```python
from rag.pipeline import KnowledgeAssistant

ka = KnowledgeAssistant()
ka.ingest("data/raw/hr_leave_policy.md")
answer = ka.ask("How many sick days do I get?")
print(answer.answer, answer.citations, answer.faithfulness)
```

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz`, `/readyz` | Liveness / readiness (no auth) |
| `POST` | `/v1/documents` | Upload a file, returns `202` + `job_id` |
| `GET` | `/v1/documents?limit=&offset=` | Paginated list of indexed documents |
| `DELETE` | `/v1/documents/{source}` | Remove a document |
| `GET` | `/v1/jobs`, `/v1/jobs/{id}` | Paginated job list / job status |
| `POST` | `/v1/ask` | `{question, mode}` returns a grounded answer + citations (cached) |
| `GET` | `/v1/stats` | Cache hit rate, queue depth, chunk count |

All `/v1/*` routes need the `X-API-Key` header. The server refuses requests until `RAG_API_KEYS` is configured.

## Configuration

Everything is an environment variable (see `.env.example` and `src/rag/config.py`): `RAG_API_KEYS`, `RAG_RATE_LIMIT_PER_MIN`, `RAG_MAX_UPLOAD_MB`, `RAG_CACHE_TTL_S`, `RAG_QUEUE_WORKERS`, `RAG_QUEUE_MAX_SIZE`, `RAG_EMBEDDER`, `RAG_RERANKER`, `RAG_GENERATOR`, and more.

## Project layout

```
src/rag/    engine: loaders, chunking, embeddings, vector_store, bm25, hybrid (RRF),
            reranker, generator, citations, pipeline, config
src/api/    FastAPI app: main, security, cache, jobs (queue), pagination, schemas
eval/       run_eval.py (recall@k, MRR, accuracy, citation precision, faithfulness)
data/raw/   synthetic sample documents (fictional company)
data/eval/  labelled question set
tests/      55 tests (unit, security, API flow)
.github/    CI, security, release workflows, Dependabot, PR/issue templates
docs/       ARCHITECTURE.md, EXECUTION_LOG.md (step-by-step build log)
```

## Scaling notes

The service is **stateless apart from `/data`**, so replicas can share a volume or, better, an external Chroma server. Cache and job queue sit behind tiny interfaces: swap `TTLCache` for Redis and `JobQueue` for Celery/RQ to scale horizontally. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full reasoning and the known limits.

## Roadmap

- [x] Retrieval engine, reranking, grounded generation, citation verification, evaluation
- [x] FastAPI, Docker, CI/CD, security hardening, caching, pagination, queueing
- [ ] Bigger eval set + neural backends (`.[ml]`, `.[llm]`) with before/after numbers
- [ ] Redis cache and Celery workers for multi-replica deployment
- [ ] AWS deployment (ECS Fargate or EKS) with Terraform
- [ ] Monitoring: Prometheus metrics, Grafana dashboard, structured tracing

## License

MIT. See [LICENSE](LICENSE). The sample documents are synthetic and describe a fictional company.
