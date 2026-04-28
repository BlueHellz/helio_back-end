"""Org / project revenue accounting (``revenue_events`` table)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from supabase import Client

EventType = str  # rev_share | marketplace_fee | pool_token_listing_fee | pool_token_trade_royalty


def log_revenue(
    supabase: Client,
    org_id: Optional[str],
    project_id: Optional[str],
    event_type: EventType,
    amount: Decimal | float,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert a row into ``revenue_events`` (call from marketplace / pool logic later)."""
    row = {
        "org_id": org_id,
        "project_id": project_id,
        "event_type": event_type,
        "amount": float(amount),
        "metadata": metadata or {},
    }
    res = supabase.table("revenue_events").insert(row).execute()
    if not res.data:
        raise RuntimeError("revenue_events insert returned no row")
    return dict(res.data[0])
