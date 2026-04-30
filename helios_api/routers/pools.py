"""Community solar pools — blended DB + seeded demo rows."""

from __future__ import annotations

from typing import Any, Dict, List

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from helios_api.db.database import get_db, record_to_api_dict
from helios_api.middleware.auth import get_current_user

router = APIRouter(prefix="/pools", tags=["pools"])

_SEED: List[Dict[str, Any]] = [
    {
        "id": "00000000-0000-4000-a000-000000000101",
        "name": "Dorchester Community Solar Pilot",
        "description": "Aggregated feeder residential portfolio",
        "target_amount_hlio": "125000",
        "raised_amount_hlio": "42000",
        "investor_count": 18,
        "governance_token_symbol": "DSL01",
        "status": "fundraising",
    },
    {
        "id": "00000000-0000-4000-a000-000000000102",
        "name": "Austin Workforce Housing Fund",
        "description": "Low-income carve-out with shared savings",
        "target_amount_hlio": "98000",
        "raised_amount_hlio": "98000",
        "investor_count": 24,
        "governance_token_symbol": "AWH01",
        "status": "active",
    },
    {
        "id": "00000000-0000-4000-a000-000000000103",
        "name": "Long Island Co-op III",
        "description": "Closed vintage — metrics met",
        "target_amount_hlio": "210000",
        "raised_amount_hlio": "210000",
        "investor_count": 40,
        "governance_token_symbol": "NYL03",
        "status": "closed",
    },
    {
        "id": "00000000-0000-4000-a000-000000000104",
        "name": "Rural TX Microgrid Sleeve",
        "description": "DER + storage revenue strip",
        "target_amount_hlio": "77500",
        "raised_amount_hlio": "12000",
        "investor_count": 11,
        "governance_token_symbol": "TXM01",
        "status": "fundraising",
    },
]


@router.get("")
async def list_pools(db: asyncpg.Connection = Depends(get_db)) -> dict[str, Any]:
    rows = await db.fetch("SELECT * FROM pools LIMIT 50")
    db_rows = [record_to_api_dict(r) for r in rows]
    merged: List[Dict[str, Any]] = _SEED.copy()
    seen = {row["id"] for row in merged}
    for row in db_rows:
        rid = str(row.get("id"))
        if rid not in seen:
            merged.append(row)
            seen.add(rid)
    return {"items": merged}


@router.get("/{pool_id}")
async def get_pool(
    pool_id: str,
    db: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    for row in _SEED:
        if row["id"] == pool_id:
            return row
    r = await db.fetchrow("SELECT * FROM pools WHERE id = $1::uuid LIMIT 1", pool_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pool not found")
    return record_to_api_dict(r)
