# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private
"Report a vulnerability" (Security tab -> Advisories) or email the maintainer. Expect an
acknowledgement within a few days.

## Controls in this project

| Threat | Mitigation |
|---|---|
| Unauthorised access | `X-API-Key` auth with constant-time comparison; **secure by default**: the API returns 503 until keys are configured. `RAG_ALLOW_ANONYMOUS` is dev-only |
| Abuse / DoS | Per-client token-bucket rate limit (429 + `Retry-After`), bounded job queue (503 backpressure), upload size cap, capped page size, bounded cache |
| Malicious uploads | Extension allow-list, magic-byte check for PDF/DOCX, binary check for text, filename sanitising (no path traversal), size limit enforced while reading |
| Prompt injection via documents | Strict system prompt (treat passages as data); plus the **citation verifier** drops any claim not supported by a retrieved passage |
| Hallucination | Abstains with "I don't know" when context lacks the answer; unsupported sentences are removed |
| Information leakage | Sources are bare file names (never server paths); API keys are never logged (only a 6-char label) |
| Container breakout | Non-root user (uid 10001), read-only root filesystem, all capabilities dropped, `no-new-privileges`, resource limits, localhost-only port binding by default |
| Supply chain | Dependabot, pip-audit, Bandit, CodeQL, gitleaks, Trivy image scan, dependency review on PRs, pinned base image tag, build provenance + SBOM on release |
| Telemetry | ChromaDB anonymous telemetry disabled |

## Known limitations (be aware before production use)

- API keys are static secrets from the environment; there is no per-user identity, RBAC, or key rotation workflow. Use a gateway / OIDC for multi-tenant use.
- Rate limiting and caching are **per process** (in memory). Behind multiple replicas, use a shared store (Redis).
- Documents are not scanned for malware, and there is no document-level access control: anyone with a valid key can query everything indexed.
- TLS is expected to terminate at a reverse proxy / load balancer.
