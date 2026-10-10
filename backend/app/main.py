from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.api.v1.api_router import api_v1_router
from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.core.middleware import TenantContextMiddleware, current_request_id
from backend.app.core.rate_limiter import RateLimiterMiddleware
from backend.app.telephony.live_dashboard_ws import router as live_dashboard_ws_router
from backend.app.telephony.media_stream import ws_router as telephony_ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure database tables exist (idempotent across SQLite & PostgreSQL)
    try:
        await init_db()
    except Exception as e:
        print(f"[Database Initialization Warning]: {e}")
    yield
    # Shutdown logic if needed


def create_application() -> FastAPI:
    app = FastAPI(
        title="CallFlow AI Backend",
        description="Production-grade AI Voice Automation Platform API",
        version="1.0.0",
        docs_url="/docs" if settings.APP_ENV != "production" or settings.DEBUG else None,
        redoc_url="/redoc" if settings.APP_ENV != "production" or settings.DEBUG else None,
        lifespan=lifespan,
    )

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Custom Tenant Context & Request Tracing Middleware
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RateLimiterMiddleware, enabled=not settings.DEBUG)

    # 3. Standard Global Exception Handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        req_id = getattr(request.state, "request_id", current_request_id.get())
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail,
                    "request_id": req_id,
                },
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", current_request_id.get())
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred." if not settings.DEBUG else str(exc),
                    "request_id": req_id,
                },
            },
        )

    # 4. System & Health Check Endpoints
    @app.get("/", tags=["System"])
    async def root():
        return {
            "status": "online",
            "app": settings.APP_NAME,
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health",
            "ready": "/ready",
            "api_v1": "/api/v1",
        }

    @app.get("/health", tags=["System"])
    async def health_check():
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/ready", tags=["System"])
    async def readiness_check():
        return {
            "ready": True,
            "environment": settings.APP_ENV,
        }

    # 5. Mount API Routers & WebSockets
    app.include_router(api_v1_router, prefix="/api")
    app.include_router(telephony_ws_router)
    app.include_router(live_dashboard_ws_router)

    return app


app = create_application()
