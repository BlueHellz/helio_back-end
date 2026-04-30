"""Marketplace listings & orders (stubs)."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from helios_api.db.database import get_db, record_to_api_dict
from helios_api.middleware.auth import get_current_user

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/listings")
async def listings(
    db: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await db.fetch("SELECT * FROM marketplace_listings LIMIT 100")
    return {"items": [record_to_api_dict(r) for r in rows]}


class OrderBody(BaseModel):
    listing_id: str
    project_id: str
    quantity: int = Field(ge=1, default=1)


@router.post("/orders")
async def create_order_stub(
    body: OrderBody,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": False,
        "message": "Order engine stub — will insert marketplace_orders when pricing wired.",
        "draft": body.model_dump() | {"buyer_id": user["id"]},
    }
