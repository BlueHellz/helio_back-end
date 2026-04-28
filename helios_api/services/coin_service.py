"""HLIO simulated balances (``hlio_wallets``, ``minting_events``)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from supabase import Client


def get_balance(supabase: Client, user_id: str) -> Decimal:
    r = (
        supabase.table("hlio_wallets")
        .select("balance")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not r.data:
        return Decimal("0")
    return Decimal(str(r.data[0]["balance"] or 0))


def transfer_hlio(
    supabase: Client,
    from_user_id: str,
    to_user_id: str,
    amount: Decimal,
) -> None:
    """Simulated transfer (two sequential updates — replace with transactional RPC later)."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    a = float(amount)
    f = (
        supabase.table("hlio_wallets")
        .select("balance,user_id")
        .eq("user_id", from_user_id)
        .limit(1)
        .execute()
    )
    if not f.data:
        raise ValueError("sender wallet missing")
    bal = Decimal(str(f.data[0]["balance"] or 0))
    if bal < amount:
        raise ValueError("insufficient HLIO balance")
    supabase.table("hlio_wallets").update({"balance": float(bal - amount)}).eq(
        "user_id", from_user_id
    ).execute()
    t = (
        supabase.table("hlio_wallets")
        .select("balance")
        .eq("user_id", to_user_id)
        .limit(1)
        .execute()
    )
    if t.data:
        tb = Decimal(str(t.data[0]["balance"] or 0))
        supabase.table("hlio_wallets").update({"balance": float(tb + amount)}).eq(
            "user_id", to_user_id
        ).execute()
    else:
        supabase.table("hlio_wallets").insert(
            {"user_id": to_user_id, "balance": float(amount)}
        ).execute()


def mint_on_installation(supabase: Client, project_id: str, amount_hlio: float) -> Dict[str, Any]:
    """Placeholder mint — inserts ``minting_events`` (chain tx_hash later)."""
    res = (
        supabase.table("minting_events")
        .insert(
            {
                "project_id": project_id,
                "amount_hlio": amount_hlio,
                "tx_hash": "simulated",
            }
        )
        .execute()
    )
    if not res.data:
        raise RuntimeError("mint insert failed")
    return dict(res.data[0])
