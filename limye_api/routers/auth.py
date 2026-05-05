"""Authentication — development bypass vs homeowner JWT."""

from __future__ import annotations

import binascii
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import asyncpg
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from limye_api.config import Settings, get_settings
from limye_api.middleware.auth import (
    auth_bypass_enabled,
    get_current_user,
    mock_profile_row,
    profile_dict_from_record,
    profile_from_signup,
)

public_router = APIRouter(prefix="/auth", tags=["auth"])
secured_router = APIRouter(prefix="/auth", tags=["auth"])

_MOCK_ACCESS = "dev-bypass-access-token"
_MOCK_REFRESH = "dev-bypass-refresh-token"


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    role: Literal["homeowner"] = "homeowner"


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


def _hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 390_000)
    return (
        "pbkdf2_sha256$"
        + binascii.hexlify(salt).decode("ascii")
        + "$"
        + binascii.hexlify(dk).decode("ascii")
    )


def _verify_password(pw: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("pbkdf2_sha256$"):
        return False
    parts = stored.split("$", 2)
    if len(parts) != 3:
        return False
    _, shex, hhex = parts
    try:
        salt = binascii.unhexlify(shex)
        expected = binascii.unhexlify(hhex)
    except binascii.Error:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 390_000)
    return secrets.compare_digest(dk, expected)


def _jwt_secret(settings: Settings) -> str:
    secret = (settings.JWT_SECRET or "").strip()
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "JWT_SECRET is not configured")
    return secret


def _encode_token(
    settings: Settings,
    *,
    sub: str,
    email: str | None,
    role: str,
    token_use: Literal["access", "refresh"],
) -> str:
    now = datetime.now(tz=UTC)
    ttl = (
        settings.JWT_ACCESS_SECONDS
        if token_use == "access"
        else settings.JWT_REFRESH_SECONDS
    )
    exp = now + timedelta(seconds=int(ttl))
    return jwt.encode(
        {
            "sub": sub,
            "email": email,
            "role": role,
            "token_use": token_use,
            "iat": now,
            "exp": exp,
        },
        _jwt_secret(settings),
        algorithm=settings.JWT_ALGORITHM,
    )


def _session_response_from_profile_access(
    profile: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    uid = str(profile["id"])
    access = _encode_token(
        settings,
        sub=uid,
        email=profile.get("email"),
        role=str(profile["role"]),
        token_use="access",
    )
    refresh = _encode_token(
        settings,
        sub=uid,
        email=profile.get("email"),
        role=str(profile["role"]),
        token_use="refresh",
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": settings.JWT_ACCESS_SECONDS,
        "expires_at": None,
        "token_type": "bearer",
        "user": {
            "id": uid,
            "email": profile.get("email"),
            "user_metadata": {
                "full_name": profile.get("full_name"),
                "role": profile["role"],
            },
        },
        "profile": profile,
    }


def _session_response_from_profile(prof: dict[str, Any], settings: Settings) -> dict[str, Any]:
    if auth_bypass_enabled(settings):
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
    return _session_response_from_profile_access(prof, settings)


def _mock_session_response(settings: Settings) -> dict[str, Any]:
    return _session_response_from_profile(mock_profile_row(), settings)


@public_router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: Request, body: SignupBody) -> dict[str, Any]:
    settings = get_settings()
    if auth_bypass_enabled(settings):
        prof = profile_from_signup(str(body.email), body.full_name)
        return _session_response_from_profile(prof, settings)
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool is not configured. Set DATABASE_URL.",
        )
    pwd = _hash_password(body.password)
    uid = uuid.uuid4()
    email_lc = str(body.email).strip().lower()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO profiles (
                    id, role, full_name, org_id, email, password_hash,
                    completed_projects_count
                )
                VALUES ($1::uuid, $2, $3, NULL, $4, $5, 0)
                RETURNING id, role, full_name, company_name, phone, wallet_address,
                          org_id, completed_projects_count, email
                """,
                uid,
                "homeowner",
                body.full_name,
                email_lc,
                pwd,
            )
        except asyncpg.UniqueViolationError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from e
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return _session_response_from_profile(profile_dict_from_record(row), settings)


@public_router.post("/login")
async def login(request: Request, body: LoginBody) -> dict[str, Any]:
    settings = get_settings()
    if auth_bypass_enabled(settings):
        return _mock_session_response(settings)
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool is not configured. Set DATABASE_URL.",
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, role, full_name, company_name, phone, wallet_address,
                   org_id, completed_projects_count, email, password_hash
            FROM profiles WHERE lower(email) = lower($1)
            LIMIT 1
            """,
            str(body.email).strip(),
        )
    if row is None or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    prof = profile_dict_from_record(row)
    return _session_response_from_profile_access(prof, settings)


@public_router.post("/refresh")
def refresh_token_route(body: RefreshBody) -> dict[str, Any]:
    settings = get_settings()
    if auth_bypass_enabled(settings):
        d = _mock_session_response(settings)
        return {
            k: d[k]
            for k in (
                "access_token",
                "refresh_token",
                "expires_in",
                "expires_at",
                "token_type",
                "user",
            )
        }
    try:
        payload = jwt.decode(
            body.refresh_token,
            _jwt_secret(settings),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "token_use"]},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None
    if payload.get("token_use") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")
    uid = payload.get("sub")
    role = payload.get("role") or "homeowner"
    email = payload.get("email")
    access = _encode_token(
        settings, sub=str(uid), email=email, role=str(role), token_use="access"
    )
    refresh_tok = _encode_token(
        settings, sub=str(uid), email=email, role=str(role), token_use="refresh"
    )
    return {
        "access_token": access,
        "refresh_token": refresh_tok,
        "expires_in": settings.JWT_ACCESS_SECONDS,
        "expires_at": None,
        "token_type": "bearer",
        "user": {
            "id": str(uid),
            "email": email,
            "user_metadata": {"role": role},
        },
    }


@secured_router.get("/me")
async def auth_me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return {"profile": user}
