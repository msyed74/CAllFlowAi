import time
import uuid
from contextvars import ContextVar
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variable for thread/task-local tenant isolation
current_tenant_id: ContextVar[Optional[str]] = ContextVar("current_tenant_id", default=None)
current_request_id: ContextVar[Optional[str]] = ContextVar("current_request_id", default=None)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware ensuring every request is tagged with a unique request ID,
    computes latency, and extracts tenant context for multi-tenant isolation.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()

        # 1. Request ID Generation / Propagation
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:16]}"
        current_request_id.set(req_id)
        request.state.request_id = req_id

        # 2. Tenant Context Extraction
        # Can be set via custom header, query param, or auth token in subsequent dependency
        org_id = request.headers.get("X-Organization-ID")
        current_tenant_id.set(org_id)
        request.state.organization_id = org_id

        # 3. Process Request
        response = await call_next(request)

        # 4. Attach metadata headers
        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        return response
