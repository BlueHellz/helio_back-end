"""Synthetic solar design + financial model for embedded proposal helpers (e.g. project pipeline).

Produces consistent, explainable projections from bill and tariff assumptions until
external APIs (Google Solar, tariffs) are wired in.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import AliasChoices, BaseModel, Field

# Engineering / economic assumptions (documented in response)
_DEFAULT_UTILITY_RATE_USD_PER_KWH = 0.28
_KWH_PER_KW_DC_ANNUAL = 1400.0
_COST_USD_PER_W_DC = 2.80
_FEDERAL_ITC_FRACTION = 0.30
_PANEL_WATT_STC = 400.0
_UTILITY_ESCALATION_YEARLY = 0.022
_DISCOUNT_RATE_NPV = 0.05
_RESIDUAL_BILL_FRACTION = 0.05


class DesignParams(BaseModel):
    """Inputs for synthetic proposal builders (not the public `/estimate` market endpoint)."""

    address: str = Field(min_length=1, description="Service address text")
    monthly_bill_usd: float = Field(
        ...,
        gt=0,
        validation_alias=AliasChoices("monthly_bill_usd", "monthly_bill"),
    )
    utility_rate_usd_per_kwh: float = Field(
        default=_DEFAULT_UTILITY_RATE_USD_PER_KWH,
        gt=0,
        validation_alias=AliasChoices(
            "utility_rate_usd_per_kwh",
            "utility_rate_per_kwh",
        ),
    )
    electricity_offset_fraction: float = Field(
        default=1.0,
        gt=0,
        le=1.0,
        validation_alias=AliasChoices(
            "electricity_offset_fraction",
            "offset_fraction",
            "energy_offset",
        ),
    )


def build_public_proposal(params: DesignParams) -> dict[str, Any]:
    """Return proposal + incentives + yearly financial projections (no persistence)."""
    monthly = float(params.monthly_bill_usd)
    rate = float(params.utility_rate_usd_per_kwh)
    offset = float(params.electricity_offset_fraction)

    annual_spend_pre_solar = monthly * 12.0
    annual_usage_kwh = annual_spend_pre_solar / rate if rate > 0 else 0.0
    annual_production_kwh = annual_usage_kwh * offset

    system_kw_dc = annual_production_kwh / _KWH_PER_KW_DC_ANNUAL if _KWH_PER_KW_DC_ANNUAL > 0 else 0.0
    panel_count = max(4, int(math.ceil((system_kw_dc * 1000.0) / _PANEL_WATT_STC)))

    # Harmonize rated size to integer panel count
    system_kw_dc_rated = (panel_count * _PANEL_WATT_STC) / 1000.0
    annual_production_kwh = system_kw_dc_rated * _KWH_PER_KW_DC_ANNUAL

    gross_cost = system_kw_dc_rated * 1000.0 * _COST_USD_PER_W_DC
    federal_itc_usd = gross_cost * _FEDERAL_ITC_FRACTION
    state_local_estimate_usd = 0.0
    net_cost = gross_cost - federal_itc_usd - state_local_estimate_usd

    first_year_tariff_value = annual_production_kwh * rate
    payback_years = net_cost / first_year_tariff_value if first_year_tariff_value > 0 else None

    yearly_projections: list[dict[str, Any]] = []
    cumulative_savings = 0.0
    npv = -net_cost
    for year in range(1, 26):
        escalator = (1.0 + _UTILITY_ESCALATION_YEARLY) ** (year - 1)
        escalated_annual_bill_without = annual_spend_pre_solar * escalator
        effective_rate = rate * escalator
        year_savings = annual_production_kwh * effective_rate
        cumulative_savings += year_savings
        residual_approx = escalated_annual_bill_without * _RESIDUAL_BILL_FRACTION
        spend_with_solar = max(residual_approx, escalated_annual_bill_without - year_savings)
        yearly_projections.append(
            {
                "year": year,
                "utility_spend_without_solar_usd": round(escalated_annual_bill_without, 2),
                "utility_spend_with_solar_usd": round(spend_with_solar, 2),
                "energy_savings_usd": round(year_savings, 2),
                "cumulative_savings_usd": round(cumulative_savings, 2),
                "estimated_production_kwh": round(annual_production_kwh, 2),
            }
        )
        npv += year_savings / ((1.0 + _DISCOUNT_RATE_NPV) ** year)

    financials = {
        "utility_rate_assumed_usd_per_kwh": rate,
        "annual_usage_kwh_estimate": round(annual_usage_kwh, 2),
        "annual_utility_spend_before_solar_usd": round(annual_spend_pre_solar, 2),
        "gross_system_cost_usd": round(gross_cost, 2),
        "incentives": {
            "federal_itc_percent": round(_FEDERAL_ITC_FRACTION * 100.0, 2),
            "federal_itc_usd": round(federal_itc_usd, 2),
            "state_local_estimate_usd": round(state_local_estimate_usd, 2),
        },
        "net_cost_after_incentives_usd": round(net_cost, 2),
        "first_year_energy_savings_usd": round(first_year_tariff_value, 2),
        "simple_payback_years": None if payback_years is None else round(payback_years, 2),
        "npv_25yr_usd_discount_5pct": round(npv, 2),
        "assumed_utility_escalation_annual": _UTILITY_ESCALATION_YEARLY,
        "assumed_discount_rate_npv": _DISCOUNT_RATE_NPV,
    }

    design = {
        "system_size_kw_dc": round(system_kw_dc_rated, 3),
        "panel_count": panel_count,
        "panel_watt_stc_assumed": int(_PANEL_WATT_STC),
        "estimated_annual_production_kwh": round(annual_production_kwh, 2),
        "specific_yield_kwh_per_kw_dc": _KWH_PER_KW_DC_ANNUAL,
    }

    return {
        "model": "synthetic_pipeline_v1",
        "pipeline_steps_completed": [
            "usage_inference",
            "system_sizing",
            "production_model",
            "cost_model",
            "incentive_model_it_c",
            "cashflow_projection_25yr",
        ],
        "inputs": params.model_dump(mode="json"),
        "design": design,
        "financials": financials,
        "financial_projections": yearly_projections,
        "notes": (
            "Projections use tariff and production heuristics; replace with tariffs, "
            "lid, and irradiance APIs for site-specific fidelity."
        ),
    }


__all__ = ["DesignParams", "build_public_proposal"]
