"""Supabase client (Postgres, Auth, Storage) using the service role key.

The service role key bypasses RLS. Use only on the server; never expose it to
the Flutter / web client. For user-scoped access, verify JWTs in routes and
filter by ``user_id`` (or use RLS with the anon key in future patterns).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from supabase import Client, create_client

from helios_api.config import Settings, get_settings

logger = logging.getLogger(__name__)


def build_supabase_client(settings: Settings) -> Optional[Client]:
    """Create a service-role client, or ``None`` if creds are missing in dev."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        if settings.is_production:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required in production.")
        logger.warning("Supabase not configured: missing URL or service key (dev only).")
        return None
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


def get_supabase(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Client:
    """FastAPI dependency: return the app-scoped Supabase client."""
    client: Optional[Client] = getattr(request.app.state, "supabase", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.",
        )
    return client
