"""HLIO wallet surface."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_user
from helios_api.services import coin_service
from supabase import Client

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("")
def wallet_balance(
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, str | float]:
    bal = coin_service.get_balance(supabase, str(user["id"]))
    pk = (
        supabase.table("hlio_wallets")
        .select("public_key")
        .eq("user_id", user["id"])
        .limit(1)
        .execute()
    )
    public_key = pk.data[0]["public_key"] if pk.data else None
    return {"user_id": str(user["id"]), "balance_hlio": float(bal), "public_key": public_key}


class ConnectBody(BaseModel):
    public_key: str = Field(min_length=32, description="Solana-compatible address")


@router.post("/connect")
def connect_wallet(
    body: ConnectBody,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, str]:
    uid = user["id"]
    existing = supabase.table("hlio_wallets").select("id").eq("user_id", uid).execute()
    if existing.data:
        supabase.table("hlio_wallets").update({"public_key": body.public_key}).eq(
            "user_id", uid
        ).execute()
    else:
        supabase.table("hlio_wallets").insert(
            {"user_id": uid, "public_key": body.public_key, "balance": 0}
        ).execute()
    supabase.table("profiles").update({"wallet_address": body.public_key}).eq("id", uid).execute()
    return {"public_key": body.public_key, "network": "devnet (simulated)"}
