"""HLIO wallet surface."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from helios_api.db.database import get_db
from helios_api.middleware.auth import get_current_user
from helios_api.services import coin_service

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("")
async def wallet_balance(
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, str | float]:
    bal = await coin_service.get_balance(db, str(user["id"]))
    row = await db.fetchrow(
        "SELECT public_key FROM hlio_wallets WHERE user_id = $1::uuid LIMIT 1",
        user["id"],
    )
    public_key = row["public_key"] if row else None
    return {"user_id": str(user["id"]), "balance_hlio": float(bal), "public_key": public_key}


class ConnectBody(BaseModel):
    public_key: str = Field(min_length=32, description="Solana-compatible address")


@router.post("/connect")
async def connect_wallet(
    body: ConnectBody,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, str]:
    uid = user["id"]
    existing = await db.fetchrow(
        "SELECT id FROM hlio_wallets WHERE user_id = $1::uuid LIMIT 1",
        uid,
    )
    if existing:
        await db.execute(
            "UPDATE hlio_wallets SET public_key = $2 WHERE user_id = $1::uuid",
            uid,
            body.public_key,
        )
    else:
        await db.execute(
            """
            INSERT INTO hlio_wallets (user_id, public_key, balance)
            VALUES ($1::uuid, $2, 0)
            """,
            uid,
            body.public_key,
        )
    await db.execute(
        "UPDATE profiles SET wallet_address = $2 WHERE id = $1::uuid",
        uid,
        body.public_key,
    )
    return {"public_key": body.public_key, "network": "devnet (simulated)"}
