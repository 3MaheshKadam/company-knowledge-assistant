"""FastAPI application factory.

Cross-cutting concerns live here, close to the routes:
  security   API-key auth, per-client rate limit, upload validation, security headers, CORS allow-list
  caching    answers cached by (data version, mode, normalised question); invalidated on ingest/delete
  pagination bounded offset pagination on list endpoints
  queuing    uploads return 202 + job id; a bounded worker queue ingests in the background
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from rag import __version__
from rag.config import Settings, get_settings
from rag.pipeline import KnowledgeAssistant

from .cache import TTLCache
from .jobs import JobQueue, QueueFull
from .pagination import paginate
from .schemas import AskRequest, AskResponse, CitationOut, JobAccepted, PageOut
from .security import RateLimiter, SecurityHeadersMiddleware, check_api_key, sanitize_filename, validate_upload

log = logging.getLogger("rag.api")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_app(settings: Settings | None = None, assistant: KnowledgeAssistant | None = None) -> FastAPI:
    s = settings or get_settings()
    ka = assistant or KnowledgeAssistant(s)
    cache = TTLCache(s.cache_max_items, s.cache_ttl_s)
    jobs = JobQueue(s.queue_workers, s.queue_max_size)
    limiter = RateLimiter(s.rate_limit_per_min)
    s.upload_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        jobs.start()
        yield
        jobs.stop()

    app = FastAPI(title="Company Knowledge Assistant", version=__version__, lifespan=lifespan)
    app.add_middleware(SecurityHeadersMiddleware)
    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(s.cors_origins),
                           allow_methods=["GET", "POST", "DELETE"], allow_headers=["X-API-Key", "Content-Type"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        log.info("request_id=%s method=%s path=%s status=%s ms=%.1f", rid, request.method,
                 request.url.path, response.status_code, (time.perf_counter() - start) * 1000)
        return response

    def auth(request: Request, key: Annotated[str | None, Depends(_api_key_header)]) -> str:
        client = check_api_key(key, s.api_keys, s.allow_anonymous)
        ident = client if client != "anonymous" else (request.client.host if request.client else "unknown")
        ok, retry = limiter.allow(ident)
        if not ok:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded",
                                headers={"Retry-After": str(int(retry) + 1)})
        return ident

    Auth = Annotated[str, Depends(auth)]

    # ---- health (unauthenticated, for orchestrators) ----------------------------------------
    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", tags=["ops"])
    def readyz() -> dict[str, Any]:
        return {"status": "ready", "chunks_indexed": ka.store.count(), "queue_depth": jobs.depth()}

    @app.get("/v1/stats", tags=["ops"])
    def stats(_: Auth) -> dict[str, Any]:
        return {"cache": cache.stats(), "queue_depth": jobs.depth(), "chunks": ka.store.count(),
                "data_version": ka.version}

    # ---- documents (queued ingestion) -------------------------------------------------------
    @app.post("/v1/documents", status_code=202, response_model=JobAccepted, tags=["documents"])
    async def upload(_: Auth, file: Annotated[UploadFile, File()]) -> JobAccepted:
        max_bytes = s.max_upload_mb * 1_048_576
        data = await file.read(max_bytes + 1)  # never read more than limit+1 into memory
        safe = validate_upload(file.filename or "upload", data, max_bytes)
        dest = s.upload_dir / safe
        dest.write_bytes(data)

        def work() -> dict[str, Any]:
            res = ka.ingest(dest)
            cache.clear()
            return asdict(res)

        try:
            job = jobs.submit("ingest", work)
        except QueueFull:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Ingestion queue is full, retry shortly",
                                headers={"Retry-After": "5"}) from None
        return JobAccepted(job_id=job.id, status=job.status, status_url=f"/v1/jobs/{job.id}")

    @app.get("/v1/documents", response_model=PageOut, tags=["documents"])
    def list_documents(_: Auth, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                       offset: Annotated[int, Query(ge=0)] = 0) -> dict[str, Any]:
        return paginate(ka.documents(), limit, offset)

    @app.delete("/v1/documents/{source}", tags=["documents"])
    def delete_document(source: str, _: Auth) -> dict[str, Any]:
        removed = ka.delete(sanitize_filename(source))
        if not removed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        cache.clear()
        return {"deleted_chunks": removed}

    # ---- jobs -------------------------------------------------------------------------------
    @app.get("/v1/jobs", response_model=PageOut, tags=["jobs"])
    def list_jobs(_: Auth, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                  offset: Annotated[int, Query(ge=0)] = 0) -> dict[str, Any]:
        return paginate([j.to_dict() for j in jobs.list()], limit, offset)

    @app.get("/v1/jobs/{job_id}", tags=["jobs"])
    def get_job(job_id: str, _: Auth) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
        return job.to_dict()

    # ---- question answering (cached) --------------------------------------------------------
    @app.post("/v1/ask", response_model=AskResponse, tags=["qa"])
    def ask(body: AskRequest, _: Auth) -> AskResponse:
        key = (ka.version, body.mode, " ".join(body.question.lower().split()))
        hit = cache.get(key)
        if hit is not None:
            return hit.model_copy(update={"cached": True})
        ans = ka.ask(body.question, body.mode)
        out = AskResponse(
            question=ans.question, answer=ans.answer, grounded=ans.grounded,
            faithfulness=round(ans.faithfulness, 3),
            citations=[CitationOut(marker=c.marker, source=c.source, page=c.page,
                                   chunk_id=c.chunk_id, snippet=c.snippet) for c in ans.citations],
            dropped_claims=ans.dropped_claims,
        )
        cache.set(key, out)
        return out

    return app
