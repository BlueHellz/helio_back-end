"""Internal diagnostics — no Bearer required."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from helios_api.config import Settings, get_settings
from helios_api.db.database import get_db

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/db-test")
async def db_test(db: asyncpg.Connection = Depends(get_db)) -> dict[str, Any]:
    """Ping PostgreSQL."""
    try:
        v = await db.fetchval("SELECT 1")
        return {"success": True, "one": v}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e)}


class ConfigCheckResponse(BaseModel):
    database_url_preview: str
    database_configured: bool


@router.get("/config-check", response_model=ConfigCheckResponse)
def config_check(settings: Settings = Depends(get_settings)) -> ConfigCheckResponse:
    """Reveal partial DATABASE_URL only — not full secrets."""
    raw_url = settings.DATABASE_URL or ""
    url_preview = raw_url[:16] + ("…" if len(raw_url) > 16 else "")
    return ConfigCheckResponse(
        database_url_preview=url_preview,
        database_configured=bool(raw_url.strip()),
    )
