"""Security building blocks: API-key auth, rate limiting, upload hardening, response headers."""

from __future__ import annotations

import hmac
import re
import threading
import time
from pathlib import Path

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from rag.loaders import SUPPORTED

# ---- authentication ------------------------------------------------------------------------


def check_api_key(provided: str | None, valid_keys: tuple[str, ...], allow_anonymous: bool) -> str:
    """Return a client id, or raise 401/503. Uses constant-time comparison (no timing leaks)."""
    if allow_anonymous:
        return provided or "anonymous"
    if not valid_keys:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Server has no API keys configured")
    if provided:
        for key in valid_keys:
            if hmac.compare_digest(provided.encode(), key.encode()):
                return key[:6]  # short label for rate limiting / logs (never the full key)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key",
                        headers={"WWW-Authenticate": "ApiKey"})


# ---- rate limiting (token bucket per client) ----------------------------------------------


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, client: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        if self.capacity <= 0:
            return True, 0.0
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(client, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self._buckets[client] = (tokens - 1, now)
                allowed, retry = True, 0.0
            else:
                self._buckets[client] = (tokens, now)
                allowed, retry = False, (1 - tokens) / self.rate
            if len(self._buckets) > 10_000:  # bound memory: drop full (idle) buckets
                self._buckets = {k: v for k, v in self._buckets.items() if v[0] < self.capacity}
        return allowed, retry


# ---- upload hardening ---------------------------------------------------------------------

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAGIC = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04"}


def sanitize_filename(name: str) -> str:
    """Strip directories and unsafe characters (blocks path traversal like ../../etc/passwd)."""
    base = Path(name.replace("\\", "/")).name
    base = _SAFE_NAME.sub("_", base).strip("._")
    return base[:120] or "upload"


def validate_upload(filename: str, data: bytes, max_bytes: int) -> str:
    """Return the safe file name or raise 4xx. Checks size, extension allow-list and magic bytes."""
    if len(data) > max_bytes:
        raise HTTPException(413, f"File exceeds {max_bytes // 1_048_576} MB")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    safe = sanitize_filename(filename)
    ext = Path(safe).suffix.lower()
    if ext not in SUPPORTED:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"Unsupported type. Allowed: {', '.join(sorted(SUPPORTED))}")
    magic = _MAGIC.get(ext)
    if magic and not data.startswith(magic):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File content does not match its extension")
    if ext in (".txt", ".md") and b"\x00" in data[:1024]:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Binary content in a text file")
    return safe


# ---- headers ------------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.startswith(("/docs", "/redoc")):  # Swagger UI needs its own assets
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response
