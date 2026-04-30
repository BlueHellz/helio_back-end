"""Authentication routes — development bypass returns mock session + profile."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field

from helios_api.middleware.auth import get_current_user, mock_profile_row

public_router = APIRouter(prefix="/auth", tags=["auth"])
secured_router = APIRouter(prefix="/auth", tags=["auth"])

Role = Literal["homeowner", "installer", "drone_op", "investor", "admin"]

_MOCK_ACCESS = "dev-bypass-access-token"
_MOCK_REFRESH = "dev-bypass-refresh-token"


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    role: Role


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


def _mock_session_response() -> dict[str, Any]:
    prof = mock_profile_row()
    uid = str(prof["id"])
    return {
        "access_token": _MOCK_ACCESS,
        "refresh_token": _MOCK_REFRESH,
        "expires_in": 86400,
        "expires_at": None,
        "token_type": "bearer",
        "user": {
            "id": uid,
            "email": prof["email"],
            "user_metadata": {
                "full_name": prof["full_name"],
                "role": prof["role"],
            },
        },
        "profile": prof,
    }


@public_router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(_body: SignupBody) -> dict[str, Any]:
    """Return mock user session (development bypass)."""
    return _mock_session_response()


@public_router.post("/login")
def login(_body: LoginBody) -> dict[str, Any]:
    """Return mock user session (development bypass)."""
    return _mock_session_response()


@public_router.post("/refresh")
def refresh_token_route(_body: RefreshBody) -> dict[str, Any]:
    """Return a fresh mock session."""
    d = _mock_session_response()
    return {k: d[k] for k in ("access_token", "refresh_token", "expires_in", "expires_at", "token_type", "user")}


@secured_router.get("/me")
async def auth_me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return {"profile": user}
