"""Org / project revenue accounting (``revenue_events`` table)."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, Optional

import asyncpg

from helios_api.db.database import record_to_api_dict

EventType = str  # rev_share | marketplace_fee | pool_token_listing_fee | pool_token_trade_royalty


async def log_revenue(
    conn: asyncpg.Connection,
    org_id: Optional[str],
    project_id: Optional[str],
    event_type: EventType,
    amount: Decimal | float,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert a row into ``revenue_events``."""
    row = await conn.fetchrow(
        """
        INSERT INTO revenue_events (org_id, project_id, event_type, amount, metadata)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb)
        RETURNING *
        """,
        org_id,
        project_id,
        event_type,
        float(amount),
        json.dumps(metadata or {}),
    )
    if row is None:
        raise RuntimeError("revenue_events insert returned no row")
    return record_to_api_dict(row)
