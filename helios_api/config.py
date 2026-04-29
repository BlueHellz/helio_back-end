"""Application configuration (Pydantic Settings).

All secrets and tunables are loaded from environment variables. Use
``helios_api/.env.example`` as a template. Copy the values to ``.env`` at the
**repository root** (or ``.env`` inside ``helios_api/``) for local development.
On Render, set variables in the service dashboard.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, List, Literal, Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_DIR = Path(__file__).resolve().parent
_ROOT = _PACKAGE_DIR.parent
# Load existing env files in priority order (later overrides earlier in pydantic? check - first wins in some versions)
# pydantic-settings: first file in tuple can take precedence; we use only one merge strategy - list in order
_ENV_FILES: tuple[str, ...] = tuple(
    str(p)
    for p in (_ROOT / ".env", _PACKAGE_DIR / ".env")
    if p.is_file()
)


class Settings(BaseSettings):
    """Black Light API settings."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES or None,  # type: ignore[assignment]
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App
    APP_NAME: str = "Black Light API"
    ENV: Literal["development", "production", "test"] = "development"
    LOG_LEVEL: str = "info"

    # --- Dev/testing: bypass JWT and act as mock installer user (never enable in prod)
    BYPASS_AUTH: bool = False

    # --- Supabase (service_role secret only on the server — never the anon key)
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
    )
    SUPABASE_JWT_SECRET: Optional[str] = None

    # --- AI (OpenAI client → DeepSeek; optional Qwen for global assistant)
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    QWEN_API_KEY: Optional[str] = None

    # --- External APIs
    GOOGLE_SOLAR_API_KEY: Optional[str] = None
    MAPBOX_ACCESS_TOKEN: Optional[str] = None
    NREL_API_KEY: Optional[str] = None
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None

    # --- Infra
    # Default: local Redis. On Render, use Upstash URL (``rediss://...`` for TLS).
    REDIS_URL: str = "redis://localhost:6379"
    SOLANA_RPC_URL: str = "https://api.devnet.solana.com"

    # --- CORS: comma-separated in env, or use Python defaults.
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8080",
            "https://black-light.vercel.app",
        ],
    )

    @field_validator("BYPASS_AUTH", mode="before")
    @classmethod
    def _coerce_bypass_auth(cls, v: Any) -> bool:
        """Env strings like ``true`` / ``1`` / ``yes`` → ``True`` (case-insensitive)."""
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        if isinstance(v, str):
            s = v.strip().lower()
            if not s:
                return False
            return s in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            return v
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings (one load per process)."""
    return Settings()


__all__ = ["Settings", "get_settings"]
