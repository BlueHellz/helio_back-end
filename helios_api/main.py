"""Black Light — FastAPI application factory.

Run locally (from the repository root)::

    uvicorn helios_api.main:app --reload --port 8000

Render (build installs deps; start)::

    uvicorn helios_api.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import Client

from helios_api.config import Settings, get_settings
from helios_api.db.supabase import build_supabase_client
from helios_api.routers import (
    auth,
    chat,
    contracts,
    debug,
    design,
    drone,
    marketplace,
    pools,
    projects,
    reports,
    settings as org_settings,
    wallet,
)

logger = logging.getLogger(__name__)

RedisT = redis.Redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: configure logging, connect Supabase + Redis. Shutdown: cleanup."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    logger.info("Starting %s (env=%s)", settings.APP_NAME, settings.ENV)

    app.state.settings = settings
    app.state.supabase: Optional[Client] = build_supabase_client(settings)

    app.state.redis: Optional[RedisT] = None
    r: Optional[RedisT] = None
    try:
        r = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5.0,
        )
        await r.ping()
        app.state.redis = r
        logger.info("Redis connected: %s", _redis_safe_url(settings.REDIS_URL))
    except Exception as e:  # noqa: BLE001
        if r is not None:
            try:
                await r.aclose()
            except Exception:  # noqa: BLE001
                pass
        if settings.is_production:
            logger.exception("Redis required in production: %s", e)
            raise
        logger.warning("Redis unavailable in dev (%s); cache disabled.", e)

    _log_routes(app)

    try:
        yield
    finally:
        if getattr(app.state, "redis", None) is not None:
            try:
                await app.state.redis.aclose()
            except Exception:  # noqa: BLE001
                logger.exception("Error closing Redis")
        logger.info("%s shut down.", settings.APP_NAME)


def _log_routes(app: FastAPI) -> None:
    paths: list[str] = []
    for route in app.routes:
        p = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if p:
            if methods:
                paths.append(f"{','.join(sorted(methods))} {p}")
            else:
                paths.append(p)
    for line in sorted(paths):
        logger.info("Route: %s", line)


def _redis_safe_url(url: str) -> str:
    """Redact password from redis URL for logs."""
    if "@" in url and "://" in url:
        try:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                hostpart = rest.split("@", 1)[1]
                return f"{scheme}://***@{hostpart}"
        except Exception:  # noqa: BLE001
            return "redis://***"
    return url


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build the ASGI app (allows tests to inject settings later)."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    api = "/api/v1"
    app.include_router(debug.router, prefix=api)
    app.include_router(auth.public_router, prefix=api)
    app.include_router(auth.secured_router, prefix=api)
    app.include_router(org_settings.router, prefix=api)
    app.include_router(projects.router, prefix=api)
    app.include_router(chat.router, prefix=api)
    app.include_router(design.router, prefix=api)
    app.include_router(reports.router, prefix=api)
    app.include_router(contracts.router, prefix=api)
    app.include_router(drone.router, prefix=api)
    app.include_router(pools.router, prefix=api)
    app.include_router(wallet.router, prefix=api)
    app.include_router(marketplace.router, prefix=api)

    return app


app = create_app()

__all__ = ["app", "create_app", "lifespan"]
