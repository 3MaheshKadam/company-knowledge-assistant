# feat: Company Knowledge Assistant - RAG engine, API, Docker, CI/CD

## Summary
Adds the whole project on top of the bootstrap commit:

- **RAG engine** (`src/rag`): loaders, chunking, embeddings, ChromaDB, BM25 from scratch, hybrid search + RRF, reranking, grounded generation, citation verification.
- **API** (`src/api`): FastAPI with API-key auth, rate limiting, hardened uploads, TTL cache, pagination, bounded background job queue.
- **Evaluation** (`eval/`): recall@k, MRR, answer accuracy, citation precision, faithfulness, abstention, on a synthetic corpus.
- **DevOps**: multi-stage non-root Dockerfile, hardened docker-compose, CI (lint / tests x3 Python versions / eval gate / container smoke test), security workflow (Bandit, pip-audit, CodeQL, gitleaks, Trivy), tag-driven release to GHCR, Dependabot.
- **Docs**: README, ARCHITECTURE, SECURITY, CONTRIBUTING, CHANGELOG, `docs/EXECUTION_LOG.md` (step-by-step build log).

## Testing done
- `pytest`: 55 passed, **94% coverage**
- `ruff check`: clean; `bandit -ll`: clean
- `python -m eval.run_eval`: Recall@4 0.95 across retrievers, faithfulness 1.00, abstention 1.00 (see README for caveats)
- Built the wheel, installed it in a clean venv and ran `scripts/smoke_test.sh` against a live uvicorn server: passes
- All workflow / compose / pre-commit YAML parses

## Not verified locally (please check the first CI run)
- The **Docker image build and container run**: no Docker daemon was available where this was developed. CI's `docker` job builds the image and runs the smoke test, so a red check there is the signal.
- Neural backends (`.[ml]`, `.[llm]`) are implemented but not exercised by tests.
- GitHub Actions versions (e.g. `aquasecurity/trivy-action@0.28.0`) were written from memory. Dependabot will keep them current, but verify they resolve.

## After merging
- Add CI/Security badges to the README (needs the final repo path).
- Enable GitHub Advanced Security / secret scanning and branch protection requiring the CI checks.
- Optional: add a `CODEOWNERS` file with your GitHub username.
- Tag `v0.1.0` to exercise the release workflow.
