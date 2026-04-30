"""Application configuration (Pydantic Settings).

All secrets and tunables are loaded from environment variables. Use
``helios_api/.env.example`` as a template. Copy the values to ``.env`` at the
**repository root** (or ``.env`` inside ``helios_api/``) for local development.
On Render, set variables in the service dashboard.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_DIR = Path(__file__).resolve().parent
_ROOT = _PACKAGE_DIR.parent
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

    # --- PostgreSQL (e.g. Neon ``postgresql://...``)
    DATABASE_URL: str = Field(
        default="",
        description="PostgreSQL connection URL for asyncpg",
    )

    # --- AI (OpenAI client → DeepSeek; optional Qwen for global assistant)
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    QWEN_API_KEY: str | None = None

    # --- External APIs
    GOOGLE_SOLAR_API_KEY: str | None = None
    MAPBOX_ACCESS_TOKEN: str | None = None
    NREL_API_KEY: str | None = None
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_PHONE_NUMBER: str | None = None

    # --- Infra
    REDIS_URL: str = "redis://localhost:6379"
    SOLANA_RPC_URL: str = "https://api.devnet.solana.com"

    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8080",
            "https://black-light.vercel.app",
        ],
    )

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
