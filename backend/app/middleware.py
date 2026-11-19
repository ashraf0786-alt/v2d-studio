"""Cross-cutting middleware: request IDs, rate limiting, access logging."""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse, Response

from .config import settings

log = logging.getLogger("v2d.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every response and log request timings."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            log.exception("request_error", extra={"request_id": rid, "path": request.url.path})
            raise
        elapsed = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = rid
        log.info("request", extra={
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(elapsed, 1),
        })
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP sliding-window limiter for API traffic."""

    def __init__(self, app, limit: int | None = None, window: int = 60) -> None:
        super().__init__(app)
        self.limit = limit or settings.RATE_LIMIT_PER_MINUTE
        self.window = window
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = Lock()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path in ("/api/health",):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        with self.lock:
            q = self.hits[ip]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                retry = max(1, int(self.window - (now - q[0])))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)
        return await call_next(request)
