"""Development auth: fixed mock homeowner user (no JWT)."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

from fastapi import Depends, HTTPException, status

_MOCK_USER_ID = "10000000-0000-4000-a000-000000000042"


def mock_profile_row() -> Dict[str, Any]:
    """Shape aligned with ``profiles`` + optional ``email`` for callers that expect it."""
    return {
        "id": _MOCK_USER_ID,
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
    """Dev session profile for a homeowner signup body."""
    p = mock_profile_row()
    p["email"] = email
    p["full_name"] = full_name
    return p


async def get_current_user() -> Dict[str, Any]:
    """Return the hardcoded mock homeowner profile (no DB; design for dev bypass)."""
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
