"""Internal diagnostics — no Bearer required. Rotate secrets after debugging."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from supabase import Client

from helios_api.config import Settings, get_settings
from helios_api.db.supabase import get_public_auth_supabase

router = APIRouter(prefix="/debug", tags=["debug"])


def _trunc(s: Optional[str], n: int) -> str:
    if not s:
        return ""
    return s[:n]


@router.get("/supabase-test")
def supabase_test(supabase: Client = Depends(get_public_auth_supabase)) -> dict[str, Any]:
    """Same Supabase dependency as signup; sanity-check Admin Auth (list_users)."""
    try:
        users = supabase.auth.admin.list_users()
        n = len(users)
        first_id: Optional[str]
        if n:
            u0 = users[0]
            first_id = str(getattr(u0, "id", "") or getattr(u0, "user_id", "")) or None
        else:
            first_id = None
        return {"success": True, "user_count": n, "first_user_id": first_id}
    except Exception as e:  # noqa: BLE001 — debug surface wants raw failure string
        return {"success": False, "error": str(e)}


class ConfigCheckResponse(BaseModel):
    supabase_url: str
    service_key_loaded: bool
    service_key_prefix: Optional[str]
    supabase_service_role_key_loaded: bool


@router.get("/config-check", response_model=ConfigCheckResponse)
def config_check(settings: Settings = Depends(get_settings)) -> ConfigCheckResponse:
    """Reveal partial URL/key pointers only — not full secrets."""
    raw_url = settings.SUPABASE_URL or ""
    url_preview = raw_url[:10] + ("…" if len(raw_url) > 10 else "")
    key = (settings.SUPABASE_SERVICE_KEY or "").strip()
    alias_set = bool((os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip())
    return ConfigCheckResponse(
        supabase_url=url_preview,
        service_key_loaded=bool(key),
        service_key_prefix=_trunc(key, 6) if key else None,
        supabase_service_role_key_loaded=alias_set,
    )
