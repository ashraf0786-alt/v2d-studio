"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .middleware import RateLimitMiddleware, RequestContextMiddleware
from .progress import hub
from .routers import admin_router, auth_router, billing_router, files_router, jobs_router, public_api_router
from .websocket import router as ws_router

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("v2d")


def _validate_security() -> None:
    if settings.is_production and settings.JWT_SECRET.startswith("CHANGE_ME"):
        raise RuntimeError("JWT_SECRET must be set to a long random value in production")
    if settings.is_production and settings.CORS_ORIGINS.strip() == "*":
        raise RuntimeError("Wildcard CORS is not allowed in production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_security()
    init_db()
    _recover_stale_jobs()
    hub.bind_loop(asyncio.get_running_loop())
    bridge = None
    if settings.queue_backend == "redis":
        from .queue import bridge_progress
        bridge = asyncio.create_task(bridge_progress(hub))
    log.info("startup", extra={"environment": settings.ENVIRONMENT,
                               "queue": settings.queue_backend, "storage": settings.STORAGE_BACKEND})
    try:
        yield
    finally:
        if bridge:
            bridge.cancel()


def _recover_stale_jobs() -> None:
    """Mark jobs left running/queued by a previous process as failed on restart."""
    from datetime import datetime, timedelta, timezone
    from sqlmodel import Session, select
    from .db import engine
    from .models import Job
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    statuses = ["running"] if settings.queue_backend == "redis" else ["queued", "running"]
    with Session(engine) as session:
        stale = session.exec(
            select(Job).where(Job.status.in_(statuses), Job.created_at < cutoff)
        ).all()
        for job in stale:
            job.status = "failed"
            job.error = "Interrupted by server restart"
            job.message = "Failed"
            session.add(job)
        if stale:
            session.commit()


app = FastAPI(title=settings.APP_NAME, version="0.2.0", lifespan=lifespan)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.CORS_ORIGINS.strip() == "*" else settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(jobs_router.router)
app.include_router(files_router.router)
app.include_router(billing_router.router)
app.include_router(admin_router.router)
app.include_router(public_api_router.router)
app.include_router(ws_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "environment": settings.ENVIRONMENT}


@app.exception_handler(HTTPException)
async def http_error(request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail},
                        headers=exc.headers or {})


@app.exception_handler(Exception)
async def unhandled(request, exc):  # pragma: no cover
    log.exception("unhandled_error", extra={"path": request.url.path})
    detail = str(exc) if settings.DEBUG or not settings.is_production else "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


# Serve the built frontend when present (single-process deployment).
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
