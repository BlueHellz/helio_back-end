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


def get_public_auth_supabase(settings: Settings = Depends(get_settings)) -> Client:
    """Fresh service-role Supabase client for signup / login / refresh only.

    **Why not** ``get_supabase`` (singleton on ``app.state``)? The supabase-py
    client registers auth listeners. After ``sign_in_with_password`` /
    ``refresh_session``, ``SIGNED_IN`` swaps the client's global
    ``Authorization`` header from the **service role** JWT to the **user**
    access token (see ``SyncClient._listen_to_auth_events``). A shared process
    singleton would then send end-user JWT to PostgREST/Admin on later
    requests, which breaks admin APIs and can surface as auth failures.

    A one-off client here means sign-in side effects never poison the app-wide
    singleton.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.",
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
