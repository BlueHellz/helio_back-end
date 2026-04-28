"""Marketplace listings & orders (stubs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_user
from supabase import Client

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/listings")
def listings(
    supabase: Client = Depends(get_supabase),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    r = supabase.table("marketplace_listings").select("*").limit(100).execute()
    return {"items": r.data or []}


class OrderBody(BaseModel):
    listing_id: str
    project_id: str
    quantity: int = Field(ge=1, default=1)


@router.post("/orders")
def create_order_stub(
    body: OrderBody,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    return {
        "ok": False,
        "message": "Order engine stub — will insert marketplace_orders when pricing wired.",
        "draft": body.model_dump() | {"buyer_id": user["id"]},
    }
