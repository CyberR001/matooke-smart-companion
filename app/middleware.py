"""Cross-cutting HTTP concerns: request IDs, security headers, basic rate limiting."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import ClassVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import settings

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
# Swagger UI loads its assets from a CDN, so the API docs get a relaxed policy.
DOCS_CSP = (
    "default-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Adds X-Request-ID and security headers to every response."""

    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if "content-security-policy" not in response.headers:
            docs = request.url.path.startswith(("/api/docs", "/api/redoc"))
            response.headers["Content-Security-Policy"] = DOCS_CSP if docs else CSP
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client sliding window on writes (POST/PUT/PATCH/DELETE).

    In-memory, so it is per process: enough to stop accidental floods on a
    single free-tier instance, not a substitute for a gateway or real auth.
    """

    WRITE: ClassVar[set[str]] = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        limit = settings.rate_limit_per_min
        if limit and request.method in self.WRITE:
            fwd = request.headers.get("x-forwarded-for", "")
            client = fwd.split(",")[0].strip() or (request.client.host if request.client else "?")
            now = time.monotonic()
            window = self.hits[client]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= limit:
                return JSONResponse(
                    {"detail": "Too many requests. Please wait a minute and try again."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            window.append(now)
        return await call_next(request)
