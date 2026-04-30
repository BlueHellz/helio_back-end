"""Development auth: fixed mock installer user (no JWT)."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

import asyncpg
from fastapi import Depends, HTTPException, status

from helios_api.db.database import get_db
from helios_api.db.init_db import MOCK_ORG_ID

_MOCK_USER_ID = "10000000-0000-4000-a000-000000000042"


def mock_profile_row() -> Dict[str, Any]:
    """Shape aligned with ``profiles`` + optional ``email`` for callers that expect it."""
    return {
        "id": _MOCK_USER_ID,
        "role": "installer",
        "full_name": "Mock Installer",
        "company_name": None,
        "phone": None,
        "wallet_address": None,
        "org_id": MOCK_ORG_ID,
        "completed_projects_count": 0,
        "email": "mock@light.io",
    }


async def ensure_mock_org_exists(conn: asyncpg.Connection) -> None:
    """Ensure mock org exists for FK constraints (pipelines, etc.)."""
    row = await conn.fetchrow("SELECT id FROM orgs WHERE id = $1::uuid", MOCK_ORG_ID)
    if row is not None:
        return
    await conn.execute(
        "INSERT INTO orgs (id, name) VALUES ($1::uuid, $2)",
        MOCK_ORG_ID,
        "Mock Org",
    )


async def get_current_user(db: asyncpg.Connection = Depends(get_db)) -> Dict[str, Any]:
    """Return the hardcoded mock installer profile."""
    await ensure_mock_org_exists(db)
    return mock_profile_row()


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


async def require_org_member(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Require ``profiles.org_id`` (mock user always has one)."""
    if not user.get("org_id"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Organization membership required",
        )
    return user
