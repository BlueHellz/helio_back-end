"""PostgreSQL access via asyncpg (Neon / direct Postgres)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


def record_to_api_dict(r: asyncpg.Record) -> dict[str, Any]:
    """Match JSON shapes clients expect (UUID/str, datetime ISO, numeric as float)."""
    return {k: _jsonable(v) for k, v in r.items()}


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, dict):
        return {kk: _jsonable(vv) for kk, vv in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


async def create_pool_safe(
    dsn: str,
    *,
    min_size: int = 1,
    max_size: int = 10,
) -> asyncpg.Pool | None:
    """Create a pool or return ``None`` on failure (server stays up)."""
    cleaned = (dsn or "").strip()
    if not cleaned:
        return None
    try:
        return await asyncpg.create_pool(dsn=cleaned, min_size=min_size, max_size=max_size)
    except Exception:
        logger.exception("asyncpg.create_pool failed; continuing without DB pool")
        return None


async def get_db(request: Request) -> AsyncGenerator[asyncpg.Connection, None]:
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool is not configured. Set DATABASE_URL.",
        )
    async with pool.acquire() as conn:
        yield conn


__all__ = ["create_pool_safe", "get_db", "record_to_api_dict"]
