"""JWT-based auth dependencies (Supabase HS256)."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, FrozenSet, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from helios_api.config import get_settings
from helios_api.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)

# Stable UUID for BYPASS_AUTH mock user (must match JWT ``sub`` shape / DB UUID columns).
_MOCK_USER_ID = "10000000-0000-4000-a000-000000000042"


def _mock_jwt_claims() -> Dict[str, Any]:
    return {"sub": _MOCK_USER_ID, "role": "installer", "email": "mock@light.io"}


def _mock_profile_row() -> Dict[str, Any]:
    """Shape aligned with ``profiles`` + optional ``email`` for callers that expect it."""
    return {
        "id": _MOCK_USER_ID,
        "role": "installer",
        "full_name": "Mock Installer",
        "company_name": None,
        "phone": None,
        "wallet_address": None,
        "org_id": None,
        "completed_projects_count": 0,
        "email": "mock@light.io",
    }


def _decode_access_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.SUPABASE_JWT_SECRET:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Auth not configured (SUPABASE_JWT_SECRET missing)",
        )
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc
    return payload


def verify_token(
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_security)],
) -> Dict[str, Any]:
    """Decode Bearer JWT to claims, or return mock claims when ``BYPASS_AUTH`` is on."""
    settings = get_settings()
    if settings.BYPASS_AUTH:
        return _mock_jwt_claims()
    if creds is None or (creds.scheme or "").lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_access_token(creds.credentials)


def get_current_user(
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_security)],
    supabase: Client = Depends(get_supabase),
) -> Dict[str, Any]:
    """Verify Bearer JWT and return the **profiles** row for ``sub``."""
    settings = get_settings()
    if settings.BYPASS_AUTH:
        if settings.is_production:
            logger.warning("BYPASS_AUTH is enabled (mock installer); do not use in production.")
        return _mock_profile_row()

    payload = verify_token(creds)
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing sub claim")

    res = supabase.table("profiles").select("*").eq("id", uid).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User profile not found")
    return dict(res.data[0])


def require_role(*roles: str):
    """Dependency factory: allow only listed ``profiles.role`` values."""

    allowed: FrozenSet[str] = frozenset(roles)

    def _checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this resource",
            )
        return user

    return _checker


get_current_homeowner = require_role("homeowner")
get_current_installer = require_role("installer")
get_current_drone_op = require_role("drone_op")
get_current_admin = require_role("admin")


def require_org_member(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Require ``profiles.org_id`` to be set (installers / org staff)."""
    if get_settings().BYPASS_AUTH:
        return user
    if not user.get("org_id"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Organization membership required",
        )
    return user
