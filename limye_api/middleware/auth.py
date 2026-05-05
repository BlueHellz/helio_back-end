"""Auth: BYPASS_AUTH dev mock homeowner, otherwise HS256 Bearer JWT validated against PostgreSQL."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

import asyncpg
import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt.exceptions import InvalidTokenError

from limye_api.config import Settings, get_settings

MOCK_HOMEOWNER_USER_ID = "10000000-0000-4000-a000-000000000042"


def auth_bypass_enabled(settings: Settings) -> bool:
    """Bypass JWT and use the fixed mock homeowner (local / explicit dev tooling).

    **Default:** bypass in non-production environments; require JWT in production unless
    ``BYPASS_AUTH`` forces otherwise.
    """
    raw = settings.BYPASS_AUTH
    if raw is None:
        return not settings.is_production
    s = str(raw).strip().lower()
    if s in ("", "auto"):
        return not settings.is_production
    if s in ("0", "false", "no", "off"):
        return False
    return True


def mock_profile_row() -> Dict[str, Any]:
    """Shape aligned with ``profiles`` + ``email`` for callers that expect it."""
    return {
        "id": MOCK_HOMEOWNER_USER_ID,
        "role": "homeowner",
        "full_name": "Mock Homeowner",
        "company_name": None,
        "phone": None,
        "wallet_address": None,
        "org_id": None,
        "completed_projects_count": 0,
        "email": "mock@light.io",
    }


def profile_from_signup(email: str, full_name: str) -> Dict[str, Any]:
    """Dev-session profile aligned with JWT ``user.sub`` seed row when bypassing."""
    p = mock_profile_row()
    p["email"] = email
    p["full_name"] = full_name
    return p


def profile_dict_from_record(row: asyncpg.Record) -> Dict[str, Any]:
    oid = row.get("org_id")
    company = row.get("company_name")
    return {
        "id": str(row["id"]),
        "role": row["role"],
        "full_name": row.get("full_name"),
        "company_name": company,
        "phone": row.get("phone"),
        "wallet_address": row.get("wallet_address"),
        "org_id": str(oid) if oid else None,
        "completed_projects_count": row.get("completed_projects_count") or 0,
        "email": row.get("email"),
    }


async def get_current_user(request: Request) -> Dict[str, Any]:
    settings = get_settings()
    if auth_bypass_enabled(settings):
        return mock_profile_row()

    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_part = authorization.split(None, 1)[1].strip()
    secret = _jwt_secret_or_503(settings)
    try:
        payload = jwt.decode(
            token_part,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "token_use"]},
        )
    except InvalidTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    if payload.get("token_use") != "access":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token must be an access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool not available for authenticated routes",
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, role, full_name, company_name, phone, wallet_address, "
            "org_id, completed_projects_count, email FROM profiles WHERE id = $1::uuid",
            sub,
        )
        if row is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        prof = profile_dict_from_record(row)
        if payload.get("email") and prof.get("email"):
            prof["email"] = str(payload["email"])
        return prof


def _jwt_secret_or_503(settings: Settings) -> str:
    secret = (settings.JWT_SECRET or "").strip()
    if not secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET is not configured",
        )
    return secret


def require_role(*roles: str):
    """Dependency factory: allow only listed ``profiles.role`` values."""

    allowed: FrozenSet[str] = frozenset(roles)

    async def _checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
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
