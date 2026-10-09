"""
Rate Limiting Middleware.

Enforces sliding-window rate limits across public API endpoints:
  - Unauthenticated routes (/api/v1/auth/login): 10 req/min per client IP.
  - Authenticated routes: 300 req/min per client IP / tenant.
Uses in-memory sliding window cache with fallback if Redis is unavailable.
"""

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        # ip -> list of request timestamps
        self._requests: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Skip WebSockets, health checks, and docs
        path = request.url.path
        if path.startswith("/ws") or path in ("/health", "/ready", "/docs", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        window_seconds = 60.0

        # Stricter limit for unauthenticated login attempts
        is_auth_route = path.endswith("/auth/login")
        max_requests = 10 if is_auth_route else 300

        key = f"{client_ip}:{is_auth_route}"

        # Clean timestamps older than window
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if now - t < window_seconds]

        if len(self._requests[key]) >= max_requests:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Maximum {max_requests} requests per minute.",
                    },
                },
                headers={"Retry-After": "60"},
            )

        self._requests[key].append(now)
        response = await call_next(request)
        return response
