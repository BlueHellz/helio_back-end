"""Design pipeline: auth-free solar layout from address; project-scoped reruns."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AliasChoices, BaseModel, Field

from limye_api.db.database import get_db
from limye_api.routers.projects import fetch_project_by_id
from limye_api.services.proposal_estimate import DesignParams, build_public_proposal
from limye_api.services.solar_design import run_solar_design

router = APIRouter(prefix="/design", tags=["design"])


class SolarDesignRequestBody(BaseModel):
    """POST /design JSON body. Optional homeowner fields are accepted for downstream use."""

    model_config = {"extra": "ignore"}

    address: str = Field(min_length=1)
    monthly_bill_usd: float | None = Field(
        None,
        validation_alias=AliasChoices("monthly_bill_usd", "monthly_bill"),
    )
    utility_rate_usd_per_kwh: float | None = Field(
        None,
        gt=0,
        validation_alias=AliasChoices("utility_rate_usd_per_kwh", "utility_rate_per_kwh"),
    )
    roof_age_years: int | None = Field(
        None,
        ge=0,
        le=120,
        validation_alias=AliasChoices("roof_age_years", "roof_age"),
    )


@router.post("")
async def design_from_address(
    request: Request,
    body: SolarDesignRequestBody,
) -> dict[str, Any]:
    """Auth-free: Mapbox geocode → Google Solar buildingInsights → canvas-ready roof + layout."""
    settings = request.app.state.settings
    redis_client = getattr(request.app.state, "redis", None)
    try:
        return await run_solar_design(body.address, settings, redis_client)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


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
