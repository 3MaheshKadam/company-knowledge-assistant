# Changelog

All notable changes are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/), versioning follows [SemVer](https://semver.org/).

## [0.1.0] - 2026-10-06
### Added
- RAG engine: loaders (PDF/DOCX/MD/TXT), chunking, embeddings, ChromaDB store, BM25 from scratch, hybrid search with RRF, reranking, grounded generation, citation verification.
- FastAPI service with API-key auth, rate limiting, upload hardening, TTL cache, pagination and a bounded background job queue.
- Evaluation harness (recall@k, MRR, accuracy, citation precision, faithfulness, abstention) and a synthetic corpus.
- Docker (multi-stage, non-root, read-only) and docker-compose; GitHub Actions for CI, security scanning and releases.
