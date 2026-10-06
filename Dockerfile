# syntax=docker/dockerfile:1.7

# ---- builder: resolve and build wheels (build tools never reach the final image) ------------
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels .

# ---- runtime: minimal, non-root, read-only-friendly -----------------------------------------
FROM python:3.12-slim AS runtime
ARG VERSION=0.1.0
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="company-knowledge-assistant" \
      org.opencontainers.image.description="RAG service: hybrid retrieval, reranking, verified citations" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    RAG_CHROMA_DIR=/data/chroma RAG_UPLOAD_DIR=/data/uploads \
    PORT=8000

# unprivileged user with a fixed uid (works with Kubernetes runAsNonRoot)
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
 && mkdir -p /app /data/chroma /data/uploads \
 && chown -R app:app /app /data

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

WORKDIR /app
COPY --chown=app:app data/raw ./data/raw
COPY --chown=app:app scripts ./scripts
USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "/app/scripts/healthcheck.py"]

# exec form => uvicorn is PID 1 and receives SIGTERM for graceful shutdown
CMD ["sh", "-c", "exec uvicorn api.asgi:app --host 0.0.0.0 --port ${PORT} --proxy-headers --no-server-header"]
