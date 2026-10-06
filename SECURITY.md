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

## Accepted risks

| Advisory | Component | Why it is accepted | Revisit |
|---|---|---|---|
| PYSEC-2026-311 (CVE-2026-45829), PYSEC-2026-3813 (CVE-2026-45830), PYSEC-2026-3814 (CVE-2026-45833), PYSEC-2026-3815 (CVE-2026-45831) | `chromadb` 1.5.9 | All four concern ChromaDB's **HTTP server** (`/api/v2/...` endpoints and its RBAC authorization provider). This project uses only the **embedded** `PersistentClient` as a library; no Chroma server is started or exposed. No fixed release exists yet. | When `chromadb` publishes a fix, upgrade and remove the `--ignore-vuln` flags in `.github/workflows/security.yml`. **If you ever run Chroma as a server (see ARCHITECTURE.md scaling notes), these advisories apply: do not do so until they are fixed.** |

## Supply-chain hygiene for CI

Third-party security tooling is itself an attack surface. `aquasecurity/trivy-action` is pinned by commit SHA (and the Trivy binary by version) because its mutable tags were hijacked in March 2026; gitleaks is installed from a pinned release with checksum verification.

