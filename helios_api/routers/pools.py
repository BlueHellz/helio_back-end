"""Community solar pools — blended DB + seeded demo rows."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_user
from supabase import Client

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
def list_pools(supabase: Client = Depends(get_supabase)) -> dict[str, Any]:
    r = supabase.table("pools").select("*").limit(50).execute()
    db_rows = list(r.data or [])
    merged: List[Dict[str, Any]] = _SEED.copy()
    seen = {row["id"] for row in merged}
    for row in db_rows:
        rid = str(row.get("id"))
        if rid not in seen:
            merged.append(row)
            seen.add(rid)
    return {"items": merged}


@router.get("/{pool_id}")
def get_pool(
    pool_id: str,
    supabase: Client = Depends(get_supabase),
    _: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    for row in _SEED:
        if row["id"] == pool_id:
            return row
    r = supabase.table("pools").select("*").eq("id", pool_id).limit(1).execute()
    if not r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pool not found")
    return dict(r.data[0])
