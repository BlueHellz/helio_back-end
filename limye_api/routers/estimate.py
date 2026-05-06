"""Auth-free market estimate from /design output or cached design reference."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, ValidationError

from limye_api.services.market_estimate import build_market_estimate
from limye_api.services.solar_design import get_cached_solar_design

router = APIRouter(prefix="/estimate", tags=["estimate"])


class EstimateRequestBody(BaseModel):
    """Either embed design fields (as from POST /design) or reference a cached design."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    designData: dict[str, Any] | None = None
    segments: list[Any] | None = None
    activeConfig: list[Any] | None = None
    yearlyEnergyDcKwh: float | None = None
    wholeRoofStats: dict[str, Any] | None = None
    address: str | None = None
    designCacheKey: str | None = None


def _resolve_raw_design(body: EstimateRequestBody) -> dict[str, Any] | None:
    if body.designData is not None:
        return dict(body.designData)
    if (
        body.segments is not None
        and body.activeConfig is not None
        and body.yearlyEnergyDcKwh is not None
    ):
        out: dict[str, Any] = {
            "segments": body.segments,
            "activeConfig": body.activeConfig,
            "yearlyEnergyDcKwh": body.yearlyEnergyDcKwh,
        }
        if body.wholeRoofStats is not None:
            out["wholeRoofStats"] = body.wholeRoofStats
        return out
    return None


@router.post("")
async def market_estimate(
    request: Request,
    body: EstimateRequestBody,
) -> dict[str, Any]:
    """Fixed-parameter market estimate from design geometry and production (or Redis cache)."""
    raw = _resolve_raw_design(body)
    if raw is None:
        redis = getattr(request.app.state, "redis", None)
        ck = (body.designCacheKey or "").strip() or None
        addr = (body.address or "").strip() or None
        if ck:
            raw = await get_cached_solar_design(redis, cache_key=ck)
            if raw is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    "No cached design for this designCacheKey. Call POST /api/v1/design first "
                    "or pass full design fields.",
                )
        elif addr:
            raw = await get_cached_solar_design(redis, address=addr)
            if raw is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    "No cached design for this address. Call POST /api/v1/design with the same "
                    "address first, or pass full design fields.",
                )
        else:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Provide designData, or segments + activeConfig + yearlyEnergyDcKwh, "
                "or address, or designCacheKey.",
            )

    try:
        return build_market_estimate(raw)
    except ValidationError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors(include_url=False),
        ) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
