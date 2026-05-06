"""Market-value solar estimate from POST /design payload (fixed tariff and cost assumptions)."""

from __future__ import annotations

import copy
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_PANEL_WATTS = 400.0
_COST_USD_PER_KW_DC = 2500.0
_ELECTRICITY_USD_PER_KWH = 0.17
_ANNUAL_DEGRADATION_RATE = 0.005  # 0.5% output loss per year vs prior year
_FEDERAL_ITC_FRACTION = 0.30
_ANALYSIS_YEARS = 25

# Equipment as % of gross contract (typical residential install mix)
_EQUIPMENT_SPLIT = (
    ("panels", 38.0),
    ("inverter", 11.0),
    ("racking", 14.0),
    ("labor", 37.0),
)


class ResolvedSolarDesign(BaseModel):
    """Minimum design shape from /api/v1/design."""

    model_config = ConfigDict(extra="allow")

    segments: list[Any]
    activeConfig: list[Any]
    yearlyEnergyDcKwh: float = Field(gt=0)

    @field_validator("activeConfig")
    @classmethod
    def _non_empty_panels(cls, v: list[Any]) -> list[Any]:
        if not v:
            raise ValueError("activeConfig must contain at least one panel")
        return v


def _geom_series_sum_ratio(r: float, n: int) -> float:
    """Sum_{k=0}^{n-1} r^k."""
    if abs(1.0 - r) < 1e-15:
        return float(n)
    return (1.0 - math.pow(r, n)) / (1.0 - r)


def build_market_estimate(design: dict[str, Any]) -> dict[str, Any]:
    """Compute economics; ``design`` is validated then echoed under designData."""
    design_echo = copy.deepcopy(design)
    payload = ResolvedSolarDesign.model_validate(design)
    panel_count = len(payload.activeConfig)
    system_kw = panel_count * (_PANEL_WATTS / 1000.0)
    year1_kwh = float(payload.yearlyEnergyDcKwh)

    total_cost = round(system_kw * _COST_USD_PER_KW_DC, 2)
    federal_itc = round(total_cost * _FEDERAL_ITC_FRACTION, 2)
    net_cost_after_itc = round(total_cost - federal_itc, 2)

    # Production each year t (1-based) = year1 * (1-deg)^(t-1)
    retain = 1.0 - _ANNUAL_DEGRADATION_RATE
    production_sum_25 = year1_kwh * _geom_series_sum_ratio(retain, _ANALYSIS_YEARS)
    savings_25yr = round(production_sum_25 * _ELECTRICITY_USD_PER_KWH, 2)

    year1_savings = year1_kwh * _ELECTRICITY_USD_PER_KWH
    if year1_savings > 0 and net_cost_after_itc > 0:
        payback = round(net_cost_after_itc / year1_savings, 2)
    else:
        payback = None

    equipment_breakdown: list[dict[str, Any]] = []
    for category, pct in _EQUIPMENT_SPLIT:
        equipment_breakdown.append(
            {
                "category": category,
                "percent": pct,
                "amountUsd": round(total_cost * (pct / 100.0), 2),
            }
        )

    return {
        "systemSizeKw": round(system_kw, 4),
        "panelCount": panel_count,
        "annualProductionKwh": round(year1_kwh, 2),
        "totalCost": total_cost,
        "savings25yr": savings_25yr,
        "paybackYears": payback,
        "incentives": [
            {
                "name": "Federal Investment Tax Credit (ITC)",
                "type": "federal_tax_credit",
                "percentOfCost": round(_FEDERAL_ITC_FRACTION * 100.0, 1),
                "amountUsd": federal_itc,
            }
        ],
        "equipmentBreakdown": equipment_breakdown,
        "designData": design_echo,
    }


__all__ = ["ResolvedSolarDesign", "build_market_estimate"]
