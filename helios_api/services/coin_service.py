"""HLIO simulated balances (``hlio_wallets``, ``minting_events``)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

import asyncpg

from helios_api.db.database import record_to_api_dict
async def get_balance(conn: asyncpg.Connection, user_id: str) -> Decimal:
    r = await conn.fetchrow(
        "SELECT balance FROM hlio_wallets WHERE user_id = $1::uuid LIMIT 1",
        user_id,
    )
    if r is None:
        return Decimal("0")
    return Decimal(str(r["balance"] or 0))


async def transfer_hlio(
    conn: asyncpg.Connection,
    from_user_id: str,
    to_user_id: str,
    amount: Decimal,
) -> None:
    """Simulated transfer (two sequential updates — replace with transactional RPC later)."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    a = float(amount)
    f = await conn.fetchrow(
        "SELECT balance, user_id FROM hlio_wallets WHERE user_id = $1::uuid LIMIT 1",
        from_user_id,
    )
    if f is None:
        raise ValueError("sender wallet missing")
    bal = Decimal(str(f["balance"] or 0))
    if bal < amount:
        raise ValueError("insufficient HLIO balance")
    await conn.execute(
        "UPDATE hlio_wallets SET balance = $2 WHERE user_id = $1::uuid",
        from_user_id,
        float(bal - amount),
    )
    t = await conn.fetchrow(
        "SELECT balance FROM hlio_wallets WHERE user_id = $1::uuid LIMIT 1",
        to_user_id,
    )
    if t:
        tb = Decimal(str(t["balance"] or 0))
        await conn.execute(
            "UPDATE hlio_wallets SET balance = $2 WHERE user_id = $1::uuid",
            to_user_id,
            float(tb + amount),
        )
    else:
        await conn.execute(
            "INSERT INTO hlio_wallets (user_id, balance) VALUES ($1::uuid, $2)",
            to_user_id,
            a,
        )


async def mint_on_installation(
    conn: asyncpg.Connection, project_id: str, amount_hlio: float
) -> Dict[str, Any]:
    """Placeholder mint — inserts ``minting_events`` (chain tx_hash later)."""
    row = await conn.fetchrow(
        """
        INSERT INTO minting_events (project_id, amount_hlio, tx_hash)
        VALUES ($1::uuid, $2, $3)
        RETURNING *
        """,
        project_id,
        amount_hlio,
        "simulated",
    )
    if row is None:
        raise RuntimeError("mint insert failed")
    return record_to_api_dict(row)
