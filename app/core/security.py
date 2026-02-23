from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.auth import resolve_user_from_headers
from app.core.config import settings


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class InMemoryRateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _client_key(self, request: Request) -> str:
        ip = request.client.host if request.client else "unknown"
        return f"{ip}:{request.url.path}"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        if request.url.path in {"/health"}:
            return await call_next(request)

        now = time.time()
        window = settings.rate_limit_window_seconds
        limit = settings.rate_limit_requests
        key = self._client_key(request)

        with self._lock:
            q = self._events[key]
            cutoff = now - window
            while q and q[0] < cutoff:
                q.popleft()

            if len(q) >= limit:
                retry_after = max(1, int(window - (now - q[0])))
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": "Too many requests. Retry later.",
                            "retry_after_seconds": retry_after,
                        }
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            q.append(now)

        return await call_next(request)


class AuthRequiredMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.exempt_paths = {"/health"}
        self.safe_methods = {"GET", "HEAD", "OPTIONS"}

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.auth_enabled:
            return await call_next(request)

        if request.method in self.safe_methods:
            return await call_next(request)

        if request.url.path in self.exempt_paths:
            return await call_next(request)

        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        user = resolve_user_from_headers(request.headers)
        if not user:
            request_id = getattr(request.state, "request_id", None)
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "authentication_required",
                        "message": "Authentication token required for write operations.",
                        "request_id": request_id,
                    }
                },
            )

        request.state.auth_user = user
        return await call_next(request)
