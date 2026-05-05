"""Design pipeline: auth-free proposal from inputs and project-scoped reruns."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from limye_api.db.database import get_db
from limye_api.routers.projects import fetch_project_by_id
from limye_api.services.proposal_estimate import DesignParams, build_public_proposal

router = APIRouter(prefix="/design", tags=["design"])


@router.post("")
async def design_from_inputs(body: DesignParams) -> dict[str, Any]:
    """Auth-free: full synthetic design + financial projections (no DB writes)."""
    return build_public_proposal(body)


@router.post("/{project_id}")
async def run_design_pipeline(
    project_id: str,
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    row = await fetch_project_by_id(db, project_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    payload: dict[str, Any] = {
        "ok": True,
        "project_id": project_id,
        "message": (
            "Design pipeline stub — full run will orchestrate "
            "Google Solar API → layout tools → NEC → financial model."
        ),
        "steps": ["google_solar", "layout_engine", "nec_check", "proposal_pdf"],
    }
    cd = row.get("custom_data") or {}
    bill = cd.get("monthly_bill_usd")
    if bill is None:
        bill = cd.get("monthly_bill")
    addr = row.get("address")
    if bill is not None and addr:
        try:
            raw_in: dict[str, Any] = {"address": str(addr), "monthly_bill": float(bill)}
            ur = cd.get("utility_rate_usd_per_kwh") or cd.get("utility_rate_per_kwh")
            if ur is not None:
                raw_in["utility_rate_usd_per_kwh"] = float(ur)
            off = (
                cd.get("electricity_offset_fraction")
                or cd.get("offset_fraction")
                or cd.get("energy_offset")
            )
            if off is not None:
                raw_in["electricity_offset_fraction"] = float(off)
            params = DesignParams.model_validate(raw_in)
            proposal = build_public_proposal(params)
            payload["financial_projections"] = proposal.get("financial_projections")
            payload["financials"] = proposal.get("financials")
            payload["design_estimate"] = proposal.get("design")
        except Exception:
            pass
    return payload
