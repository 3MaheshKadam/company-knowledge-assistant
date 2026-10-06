# Execution log: how this project was built, step by step

This is the flow of execution: what was done, in what order, **why**, and what went wrong along the way (the bugs are the best teaching material). Read it top to bottom, then read the code in the order given in "Suggested reading order" at the end.

Date built: 2026-10-06. Branch: `feature/rag-knowledge-assistant`.

---

## Phase 0: Decisions made before writing code

| Decision | Why |
|---|---|
| New folder `company-knowledge-assistant/` next to your first project | Keeps project 1 (`Rag1-question`) untouched; each project is self-contained |
| Build every RAG component by hand (BM25, RRF, chunking, citation checks) | The goal is learning + a portfolio piece, not wiring a framework |
| **Pluggable backends with offline defaults** | CI and reviewers can run everything with no GPU, no model download and no API key. Neural models are an opt-in extra (`.[ml]`, `.[llm]`) |
| Evaluation is a first-class feature | Most portfolio RAG projects never measure anything. The results table is the differentiator |
| Secure by default | No API keys configured => the API refuses to serve rather than serving openly |
| Never commit to `main`; work on a feature branch and open a PR | Matches a real team workflow; you review and merge |
| Commits carry only your name/email, no AI co-author trailer | Requested: Claude must not appear as a contributor on your GitHub repo |

## Phase 1: Repository bootstrap

1. `git init -b main`, then a first commit with only `LICENSE` (MIT), `.gitignore`, `.gitattributes` (LF line endings, binary markers) and a stub README. This gives the PR a clean base to diff against.
2. Created branch `feature/rag-knowledge-assistant` for all real work.

**Problem 1: git couldn't finish.** The workspace folder doesn't allow deleting files by default, and git constantly creates and deletes lock/temp files (`HEAD.lock`, `tmp_obj_*`). The first `git init` failed half-way. **Fix:** granted delete permission for the workspace, removed the broken `.git`, re-initialised.

## Phase 2: The RAG engine (`src/rag/`), mapped to your roadmap

| Roadmap item | File | Notes |
|---|---|---|
| Document loading | `loaders.py` | PDF per page (pypdf), DOCX (python-docx), MD/TXT. Markdown headings are converted to standalone sentences (see Problem 5) |
| Chunking | `chunking.py` | 120-word windows, 25 overlap, deterministic SHA-1 IDs => idempotent re-ingestion |
| Embeddings | `embeddings.py` | `HashingEmbedder` (signed feature hashing of unigrams+bigrams) and `SentenceTransformerEmbedder` behind one `Embedder` protocol |
| ChromaDB | `vector_store.py` | Persistent, cosine space, we pass our own vectors, telemetry off |
| Dense retrieval | `pipeline.py::retrieve("dense")` | Embed the query, ask Chroma for the nearest chunks |
| BM25 | `bm25.py` | Hand-written Okapi BM25 (k1=1.5, b=0.75) |
| Hybrid + RRF | `hybrid.py` | `sum 1/(60+rank)` over the dense and BM25 rankings |
| Reranking | `reranker.py` | Lexical (offline) and cross-encoder (optional); applied to the top-20 hybrid candidates, keep 4 |
| LLM generation | `generator.py` | Strict grounded prompt; extractive generator offline, Anthropic generator optional |
| Citation verification | `citations.py` | Sentence-level support check + exact number match; unsupported claims dropped, `faithfulness` reported |
| Evaluation | `eval/run_eval.py` | recall@k, MRR, accuracy, citation precision, faithfulness, abstention |

**The query path**, as one trace: question -> embed -> Chroma top-20 **and** BM25 top-20 -> RRF merge -> rerank to top-4 -> generator writes sentences tagged `[1]`, `[2]` -> verifier keeps only sentences whose cited chunk supports them -> `Answer(answer, citations, faithfulness, dropped_claims)`.

## Phase 3: Sample data and evaluation set

- 5 **synthetic** documents about a fictional company (HR leave, handbook, IT security SOP, deployment runbook, expenses). Safe to publish.
- 25 labelled questions (`data/eval/questions.jsonl`): 22 answerable (with the exact keywords the answer must contain) and 3 unanswerable ("CEO's salary?", "pets?", "stock options?") to test that the system says "I don't know".
- A chunk counts as *relevant* when it contains all expected keywords.

## Phase 4: The API layer (`src/api/`)

You asked for **caching, pagination, queuing** and security. Where each lives:

| Concern | File | How it works |
|---|---|---|
| Auth | `security.py::check_api_key` | `X-API-Key`, `hmac.compare_digest` (constant time), 503 if unconfigured |
| Rate limit | `security.py::RateLimiter` | Token bucket per client; 429 + `Retry-After` |
| Upload safety | `security.py::validate_upload` | extension allow-list, PDF/DOCX magic bytes, size cap, filename sanitising (`../../evil` becomes `evil`) |
| Headers | `security.py::SecurityHeadersMiddleware` | nosniff, X-Frame-Options, CSP, no-store |
| Caching | `cache.py::TTLCache` | LRU + TTL, keyed by (data version, mode, normalised question), cleared on ingest/delete |
| Pagination | `pagination.py` | `limit` clamped to 100, returns `total` and `next_offset` |
| Queuing | `jobs.py::JobQueue` | bounded queue + worker threads; upload returns 202; full queue gives 503 + `Retry-After` |
| App wiring | `main.py::create_app` | factory function (tests inject their own settings) |

## Phase 5: Tests (55 tests, 94% coverage)

Unit tests per module (chunking, BM25, RRF math, citations, loaders including a hand-built PDF), pipeline tests against the sample corpus, security tests (traversal, bad types, 401/429/503), and a full API flow test (upload -> job -> ask -> cache hit -> invalidate on ingest -> delete).

## Phase 6: Docker and DevOps

- `Dockerfile`: multi-stage (build wheels, then copy into a slim runtime), non-root uid 10001, healthcheck, `exec` form for clean SIGTERM handling.
- `docker-compose.yml`: read-only FS, dropped capabilities, `no-new-privileges`, CPU/memory/PID limits, log rotation, volume for data, localhost-only port, plus a one-off `seed` job. `docker-compose.dev.yml` relaxes auth for local dev only.
- `.github/workflows/`: `ci.yml`, `security.yml`, `release.yml`; `dependabot.yml`; PR and issue templates; `.pre-commit-config.yaml`.
- `scripts/smoke_test.sh`: black-box end-to-end check used by CI against the container (and runnable by you).

## Problems found while building (and how they were fixed)

1. **Git lock files**: see Phase 1.
2. **Background installs died.** Each shell call kills child processes when it ends, so `pip install &` never finished. The 23 MB `chromadb` wheel also stalled in that sandbox. **Fix:** tested in a second environment with normal network access and kept the project folder as the source of truth (files verified identical by SHA-256).
3. **Settings were read at import time.** `os.environ.get(...)` as a dataclass default runs once when the module loads, so tests couldn't override env vars. **Fix:** every field uses `default_factory`, so the environment is read when `Settings()` is created.
4. **Auth returned 422 instead of 401.** FastAPI could not resolve the locally defined `Auth = Annotated[...]` alias because the file had `from __future__ import annotations` (annotations become strings and local names aren't visible), so it treated `_` as a required query parameter. **Fix:** removed that import from `main.py`. Lesson: don't combine postponed annotations with locally defined dependency aliases.
5. **Chunking flattened newlines, so markdown headings glued onto sentences** ("## Annual Leave Full-time employees...") and the extractive generator picked weak sentences. A first fix (skip lines that start with `#`) made accuracy collapse to 0.45 because after flattening *every chunk* is one line starting with `#`. **Real fix:** convert headings to standalone sentences at load time ("Annual Leave."). Lesson: fix problems where the information is lost, not downstream.
6. **`Retry-After` header missing on 503.** Headers set on the injected `Response` are discarded when you raise `HTTPException`. **Fix:** pass `headers=` to the exception.
7. **Bandit flagged md5/sha1.** They're used for hashing features and IDs, not security. **Fix:** `usedforsecurity=False` (honest fix, no `# nosec`).
8. **Eval finding, not a bug:** "minimum password length" misses because the document says "at least 14 characters long". Pure lexical retrieval can't bridge that; it's the motivation for neural embeddings.

## What was verified, and what was not

Verified: 55 tests pass; ruff and bandit clean; wheel builds and installs in a clean environment; a live server passed `smoke_test.sh` (auth, queued ingest, grounded answer with citation, cache hit); YAML files parse; eval numbers are real outputs.

**Not verified:** the Docker image itself was never built or run (no Docker daemon available during development); the first CI run on GitHub will do it. Neural backends were not exercised.

## Git history on this branch

Conventional-commit style, one logical change per commit, authored by you. See `git log --oneline main..HEAD`.

## Suggested reading order (to learn it)

1. `src/rag/types.py`, `text.py`: the vocabulary.
2. `chunking.py`, `loaders.py`: getting text in.
3. `embeddings.py`, `vector_store.py`: dense retrieval.
4. `bm25.py`: sparse retrieval (read the formula in the docstring, then the code).
5. `hybrid.py`: RRF in 15 lines.
6. `reranker.py`: why a second stage helps.
7. `generator.py`, `citations.py`: grounding and verification (the part interviewers ask about).
8. `pipeline.py`: how it all connects.
9. `eval/run_eval.py` and `tests/`: how quality is measured.
10. `src/api/*`, `Dockerfile`, `.github/workflows/*`: the engineering around the model.

## Try it yourself

```bash
pip install -e ".[dev]" && pytest && python -m eval.run_eval
RAG_ALLOW_ANONYMOUS=true uvicorn api.asgi:app --app-dir src      # then open /docs
docker compose up --build                                        # the container version
```
Experiments: change `RAG_CHUNK_SIZE`, drop the reranker, add your own question to `data/eval/questions.jsonl`, and watch the table move.
