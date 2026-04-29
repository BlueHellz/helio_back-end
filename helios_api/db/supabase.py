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
from supabase.lib.client_options import DEFAULT_HEADERS, SyncClientOptions

from helios_api.config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_service_role_supabase_client(settings: Settings) -> Client:
    """PostgREST client with explicit ``apikey`` + ``Authorization: Bearer <service_role>``."""
    supabase_url = (settings.SUPABASE_URL or "").strip()
    service_role_key = (settings.SUPABASE_SERVICE_KEY or "").strip()
    auth_headers = {
        **DEFAULT_HEADERS.copy(),
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    options = SyncClientOptions(headers=auth_headers)
    return create_client(supabase_url, service_role_key, options=options)


def build_supabase_client(settings: Settings) -> Optional[Client]:
    """Create a service-role client, or ``None`` if creds are missing in dev."""
    supabase_url = (settings.SUPABASE_URL or "").strip()
    service_role_key = (settings.SUPABASE_SERVICE_KEY or "").strip()
    if not supabase_url or not service_role_key:
        if settings.is_production:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required in production.")
        logger.warning("Supabase not configured: missing URL or service key (dev only).")
        return None
    return create_service_role_supabase_client(settings)


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

    Always uses ``SUPABASE_SERVICE_KEY`` (service_role JWT) from settings — never
    the anon key. Passes explicit ``apikey`` + ``Authorization: Bearer …`` on the
    client options so Auth Admin endpoints see ``service_role`` (GoTrue rejects
    admin calls missing these roles otherwise).

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
    supabase_url = (settings.SUPABASE_URL or "").strip()
    service_role_key = (settings.SUPABASE_SERVICE_KEY or "").strip()
    if not supabase_url or not service_role_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.",
        )
    return create_service_role_supabase_client(settings)
