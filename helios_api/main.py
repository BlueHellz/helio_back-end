"""Black Light — FastAPI application factory.

Run locally (from the repository root)::

    uvicorn helios_api.main:app --reload --port 8000

Render (build installs deps; start)::

    uvicorn helios_api.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from helios_api.config import Settings, get_settings
from helios_api.db.database import create_pool_safe
from helios_api.db.init_db import init_database, seed_mock_org
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


def _error_cors_headers() -> dict[str, str]:
    """Broad ACAO for error JSON so browsers surface status/body instead of opaque CORS failures.

    Uses ``*`` only (no ``Access-Control-Allow-Credentials``) so the combination stays spec-valid.
    """
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: logging, asyncpg pool, Redis. Shutdown: cleanup."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    logger.info("Starting %s (env=%s)", settings.APP_NAME, settings.ENV)

    app.state.settings = settings

    dsn = (settings.DATABASE_URL or "").strip()
    app.state.pool = await create_pool_safe(dsn)
    if app.state.pool is not None:
        logger.info("PostgreSQL pool ready")
        try:
            await init_database(app.state.pool)
            await seed_mock_org(app.state.pool)
        except Exception:
            logger.exception("Database schema initialization failed")
            raise
    elif dsn:
        logger.warning("DATABASE_URL is set but pool creation failed; /health reports database unavailable")
    elif settings.is_production:
        logger.warning("DATABASE_URL is empty in production; API database routes will return 503")
    else:
        logger.warning("DATABASE_URL not set; API database calls will return 503")

    app.state.redis: RedisT | None = None
    r: RedisT | None = None
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
        pool = getattr(app.state, "pool", None)
        if pool is not None:
            await pool.close()
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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app (allows tests to inject settings later)."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
    )

    cors_origins: list[str] = list(settings.CORS_ORIGINS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        body: Any = exc.detail
        if isinstance(body, str):
            content: dict[str, Any] = {"detail": body}
        else:
            content = {"detail": body}
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=_error_cors_headers(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
            headers=_error_cors_headers(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception during request")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers=_error_cors_headers(),
        )

    @app.get("/health", tags=["health"], summary="Liveness probe")
    async def health(request: Request) -> dict[str, str]:
        pool_ok = getattr(request.app.state, "pool", None) is not None
        if pool_ok:
            return {"status": "ok", "database": "connected"}
        return {
            "status": "degraded",
            "database": "unavailable",
            "warning": "PostgreSQL pool is not available; check DATABASE_URL and logs",
        }

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
