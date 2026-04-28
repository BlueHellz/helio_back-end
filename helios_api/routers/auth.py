"""Authentication routes (Supabase Auth + ``profiles`` upsert)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from supabase import Client
from supabase_auth.errors import AuthApiError

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

Role = Literal["homeowner", "installer", "drone_op", "investor", "admin"]


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


def _session_blob(session: Any, user: Any) -> dict[str, Any]:
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_in": getattr(session, "expires_in", None),
        "expires_at": getattr(session, "expires_at", None),
        "token_type": getattr(session, "token_type", "bearer"),
        "user": {
            "id": str(user.id),
            "email": getattr(user, "email", None),
            "user_metadata": getattr(user, "user_metadata", {}) or {},
        },
    }


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupBody, supabase: Client = Depends(get_supabase)) -> dict[str, Any]:
    """Create auth user + profile row, then return a fresh session (JWT pair)."""
    try:
        cu = supabase.auth.admin.create_user(
            {
                "email": body.email,
                "password": body.password,
                "email_confirm": True,
                "user_metadata": {"full_name": body.full_name},
            }
        )
        uid = str(cu.user.id)
    except AuthApiError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        supabase.table("profiles").insert(
            {
                "id": uid,
                "role": body.role,
                "full_name": body.full_name,
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001 — profile insert failed — best-effort rollback
        try:
            supabase.auth.admin.delete_user(uid)
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Profile creation failed: {exc}",
        ) from exc

    try:
        si = supabase.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
        if not si.session:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No session after signup")
        return {
            **_session_blob(si.session, si.user),
            "profile": {
                "id": uid,
                "role": body.role,
                "full_name": body.full_name,
            },
        }
    except AuthApiError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/login")
def login(body: LoginBody, supabase: Client = Depends(get_supabase)) -> dict[str, Any]:
    """Password grant — returns Supabase session tokens."""
    try:
        si = supabase.auth.sign_in_with_password({"email": body.email, "password": body.password})
        if not si.session:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        profile = (
            supabase.table("profiles").select("*").eq("id", str(si.user.id)).limit(1).execute()
        )
        prof = profile.data[0] if profile.data else None
        return {**_session_blob(si.session, si.user), "profile": prof}
    except AuthApiError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh")
def refresh_token(body: RefreshBody, supabase: Client = Depends(get_supabase)) -> dict[str, Any]:
    """Exchange refresh token for a new session."""
    try:
        si = supabase.auth.refresh_session(body.refresh_token)
        if not si.session:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unable to refresh session")
        return _session_blob(si.session, si.user)
    except AuthApiError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/me")
def auth_me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return JWT-authenticated profile."""
    return {"profile": user}
