"""LIMYÈ AI configuration: prompt-to-interface orchestration via DeepSeek."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Final

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError as OpenAIAPIError
from pydantic import BaseModel, Field

from helios_api.db.database import get_db, record_to_api_dict
from helios_api.middleware.auth import require_org_member
from helios_api.services.ai_brain import deepseek_chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["limye-ai"])

_FIELD_TYPES: Final[frozenset[str]] = frozenset(
    {
        "text",
        "number",
        "date",
        "dropdown",
        "multi_select",
        "file",
        "photo",
        "toggle",
        "url",
        "phone",
        "email",
        "currency",
        "formula",
    }
)

_CUSTOM_COMPONENT_ENSURE: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS custom_component_definitions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        component_type TEXT NOT NULL,
        props JSONB DEFAULT '{}',
        target_sections JSONB DEFAULT '[]',
        created_at TIMESTAMPTZ DEFAULT now()
    )
    """.strip(),
    "CREATE INDEX IF NOT EXISTS idx_custom_component_definitions_org_id ON custom_component_definitions(org_id)",
)

# All 67 LIMYÈ catalog components (canonical order requested by product).
_COMPONENT_NAMES: Final[tuple[str, ...]] = (
    "ContactCard",
    "CompanyCard",
    "DealCard",
    "PipelineBoard",
    "PipelineStageColumn",
    "ActivityTimeline",
    "ActivityScheduler",
    "LeadInbox",
    "LeadScoringWidget",
    "EmailIntegrationPanel",
    "CallDialerWidget",
    "CustomFieldText",
    "CustomFieldNumber",
    "CustomFieldDate",
    "CustomFieldDropdown",
    "CustomFieldMultiSelect",
    "CustomFieldFile",
    "CustomFieldPhoto",
    "CustomFieldToggle",
    "CustomFieldURL",
    "CustomFieldPhone",
    "CustomFieldEmail",
    "CustomFieldCurrency",
    "CustomFieldFormula",
    "CustomModule",
    "FormBuilder",
    "IntakeForm",
    "DashboardMetricsGrid",
    "RevenueChart",
    "PipelineFunnelChart",
    "ForecastTable",
    "DataTable",
    "ListView",
    "CardGridView",
    "CalendarView",
    "TimelineGanttView",
    "SearchBar",
    "FilterPanel",
    "SegmentsTool",
    "QuickActionsMenu",
    "NotificationCenter",
    "WorkflowAutomationRule",
    "BlueprintBuilder",
    "RolePermissionManager",
    "APIKeyManager",
    "WebhookConfigurationPanel",
    "IntegrationMarketplace",
    "MobileResponsiveShell",
    "UserProfileCard",
    "BillingPlanManager",
    "AIChatAssistantPanel",
    "AISolarDesignSummaryCard",
    "RoofAnalysisViewer",
    "PermitReadyPlanSetGenerator",
    "FinancialSavingsProjectionCard",
    "InstallerMatchingCard",
    "FinancingOfferCard",
    "CommunityPoolInvestmentCard",
    "DroneOpJobCard",
    "HLIOWalletBalanceChip",
    "AISalesCoachPanel",
    "AutoDispositioningRuleCard",
    "AIGeneratedCallSummaryCard",
    "PromptToInterfaceBox",
    "FlowMeshNodeGraphEditor",
    "CustomComponentBuilder",
    "CustomComponentLibrary",
)

_PROPERTY_CONSTRAINT_OVERRIDES: Final[dict[str, str]] = {
    "ContactCard": "props: bindingKey(contact|lead entity), emphasizedFields[]; constraints: show up to four inline fields.",
    "CompanyCard": "props: bindingKey(account|company entity); constraints: summarize firmographics only.",
    "DealCard": "props: bindingKey(deal entity), headlineField id; constraints: exposes stage + amount KPIs.",
    "PipelineBoard": "props: pipelineId|null (server resolves), lanes[] of stage refs; constraints: lanes map 1:1 to pipeline_stage columns.",
    "PipelineStageColumn": "props: stageId|string key, collapsible(bool); constraints: nests DealCard/ListView.",
    "IntakeForm": "props: formId|string; constraints: submits to configured intake webhook key only.",
    "FormBuilder": "props: editingMode(bool); constraints: authoring only for builders; read-only elsewhere.",
    "CustomModule": "props: moduleKey; constraints: must bundle registered custom_field bindings.",
}


def _component_catalog_documentation() -> str:
    lines: list[str] = []
    generic = (
        "Standard props: bindingKey?, dataSource?, entityRefs[] (typed ids), ariaLabel?, featureFlags[]. "
        "Constraints: subtree children must cite only catalog types; forbid raw markup; forbid embedding secrets."
    )
    for i, name in enumerate(_COMPONENT_NAMES, start=1):
        extra = _PROPERTY_CONSTRAINT_OVERRIDES.get(name)
        suffix = extra if extra else generic
        lines.append(f"{i}. {name} — {suffix}")
    assert len(_COMPONENT_NAMES) == 67
    return "\n".join(lines)


def _limye_configure_system_prompt() -> str:
    catalog = _component_catalog_documentation()
    field_types_line = "'" + "', '".join(sorted(_FIELD_TYPES)) + "'"
    return f"""You are LIMYÈ — the configuration brain for HELIO CRM / solar installers.

## Component catalog ({len(_COMPONENT_NAMES)} catalog types)
Each catalog type lists properties and behavioral constraints usable inside A2UI JSON:
{catalog}

## LIMYÈ design language
Background F8F9FA (light mode) or 0B1E33 (dark); cards white or 111F2F with 1px borders and 16px corner radius—never shadows, never gradients.
Accent 0066FF, secondary green 00A86B, body copy 5F6B7A or 8A9BB5. Typography stays sans-serif with JetBrains Mono reserved for monospace data cells.
IMPORTANT: Never specify literal colors, font families, point sizes, or spacing numbers in JSON you emit—the renderer applies tokens only.

## CRM domain grounding
Assume deals move through pipelines (stages ordering revenue), intake captures leads through forms/dashboards tied to pipelines, dashboards chart pipeline health and forecasting, solar workflows weave site visits, permitting, installs, financings, wallets, drones, installers, permitting packages, HLIO payouts. Prefer mutations that hydrate those flows.

## API surface DeepSeek orchestrates via internal_mutations (executed server-side)
Use these mutation shapes only (each mutation object includes a string "type" discriminator):

1. create_pipeline → mirrors REST POST `/api/v1/org/pipelines`
   fields: type, name(string), stages(array of objects with name, order_index(integer), optional color hex string defaults to `#0066FF`).

2. create_custom_field → mirrors REST POST `/api/v1/org/custom-fields`
   fields: type, name(string), field_type(one of {field_types_line}), optional arrays options/target_sections(default []), booleans/strings per settings route defaults.

3. save_layout → mirrors REST POST `/api/v1/org/layout/{{section}}`
   fields: type, section(string), payload(object persisted as JSONB layout blob).

## Response JSON contract
Return **only valid JSON** (no markdown fences) with exactly two keys: "ui" (object containing the generated A2UI tree using ONLY the catalog PascalCase components) and "internal_mutations" (array of mutations in execution order).

The `"ui"` value must be declarative, semantic-only, and tree-shaped with catalog component identifiers referenced via each node's canonical type tokens.
"""


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    try:
        obj, end = decoder.raw_decode(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model output was not JSON: {exc}") from exc
    if end < len(text.strip()):
        # tolerate trailing prose only if decoded prefix is entire meaningful doc
        pass
    if not isinstance(obj, dict):
        raise ValueError("Model JSON root must be an object")
    return obj


async def _ensure_custom_component_table(conn: asyncpg.Connection) -> None:
    for stmt in _CUSTOM_COMPONENT_ENSURE:
        await conn.execute(stmt)


async def _execute_limye_mutations(
    conn: asyncpg.Connection,
    org_id: str,
    mutations_in: Any,
) -> list[str]:
    if mutations_in is None:
        return []
    if not isinstance(mutations_in, list):
        raise ValueError("internal_mutations must be an array")
    summaries: list[str] = []
    oid = org_id

    async with conn.transaction():
        for idx, mutation in enumerate(mutations_in):
            if not isinstance(mutation, dict):
                raise ValueError(f"mutation[{idx}] must be an object")
            m_type = mutation.get("type")
            if m_type == "create_pipeline":
                name = mutation.get("name")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(f"mutation[{idx}].create_pipeline requires name")
                stages = mutation.get("stages") or []
                row = await conn.fetchrow(
                    "INSERT INTO pipelines (org_id, name) VALUES ($1::uuid, $2) RETURNING id",
                    oid,
                    name.strip(),
                )
                if row is None:
                    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "pipeline insert failed")
                pid = str(row["id"])
                for si, stage in enumerate(stages):
                    if not isinstance(stage, dict):
                        raise ValueError(f"mutation[{idx}].stages[{si}] invalid")
                    sname = stage.get("name")
                    order_index = stage.get("order_index")
                    color = stage.get("color") or "#0066FF"
                    if not isinstance(sname, str) or not isinstance(order_index, int):
                        raise ValueError(f"mutation[{idx}].stages[{si}] requires name(str) & order_index(int)")
                    await conn.execute(
                        """
                        INSERT INTO pipeline_stages (pipeline_id, name, order_index, color)
                        VALUES ($1::uuid, $2, $3, $4)
                        """,
                        pid,
                        sname,
                        order_index,
                        str(color),
                    )
                summaries.append(
                    f"POST /api/v1/org/pipelines — created '{name.strip()}' with {len(stages)} stage(s) (id={pid})"
                )

            elif m_type == "create_custom_field":
                name = mutation.get("name")
                ft = mutation.get("field_type")
                if not isinstance(name, str) or not isinstance(ft, str):
                    raise ValueError(f"mutation[{idx}] create_custom_field requires name & field_type")
                if ft not in _FIELD_TYPES:
                    raise ValueError(f"mutation[{idx}] unknown field_type {ft!r}")
                options = mutation.get("options") or []
                is_global = bool(mutation.get("is_global", False))
                target_sections = mutation.get("target_sections") or []
                visibility_rules = mutation.get("visibility_rules") if isinstance(mutation.get("visibility_rules"), dict) else {}
                sort_order = int(mutation.get("sort_order") or 0)
                required = bool(mutation.get("required") or False)
                nrow = await conn.fetchrow(
                    """
                    INSERT INTO custom_field_definitions (
                        org_id, name, field_type, options, is_global, target_sections,
                        visibility_rules, sort_order, required
                    ) VALUES (
                        $1::uuid, $2, $3, $4::jsonb, $5, $6::jsonb, $7::jsonb, $8, $9
                    ) RETURNING id
                    """,
                    oid,
                    name.strip(),
                    ft,
                    json.dumps(options),
                    is_global,
                    json.dumps(target_sections),
                    json.dumps(visibility_rules),
                    sort_order,
                    required,
                )
                if nrow is None:
                    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "custom_field insert failed")
                summaries.append(
                    f"POST /api/v1/org/custom-fields — created field '{name.strip()}' ({ft}) "
                    f"(id={nrow['id']})"
                )

            elif m_type == "save_layout":
                section = mutation.get("section")
                payload = mutation.get("payload")
                if not isinstance(section, str) or not section.strip():
                    raise ValueError(f"mutation[{idx}] save_layout needs section(string)")
                if payload is None or not isinstance(payload, dict):
                    raise ValueError(f"mutation[{idx}] save_layout needs payload(object)")
                await conn.execute(
                    """
                    INSERT INTO org_layouts (org_id, section, layout, updated_at)
                    VALUES ($1::uuid, $2, $3::jsonb, now())
                    ON CONFLICT (org_id, section) DO UPDATE SET
                        layout = EXCLUDED.layout,
                        updated_at = now()
                    """,
                    oid,
                    section.strip(),
                    json.dumps(payload),
                )
                summaries.append(f"POST /api/v1/org/layout/{section.strip()} — layout upserted")
            else:
                raise ValueError(f"unsupported mutation type {m_type!r}")

    return summaries


class ConfigurePromptBody(BaseModel):
    prompt: str = Field(min_length=1)


@router.post("/ai/configure")
async def ai_configure(
    body: ConfigurePromptBody,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    system_prompt = _limye_configure_system_prompt()
    user_prompt = body.prompt.strip()

    try:
        raw_completion = await deepseek_chat_completion(system_prompt, user_prompt)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OpenAIAPIError as exc:
        logger.exception("DeepSeek failure during configure")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek unavailable: {exc}",
        ) from exc

    try:
        decoded = _extract_json_object(raw_completion)
    except ValueError as exc:
        logger.warning("Configure output parse failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="DeepSeek completed but produced invalid JSON.",
        ) from exc

    ui_raw = decoded.get("ui")
    ui_out = ui_raw if isinstance(ui_raw, dict) else {}

    org_id = str(user["org_id"])
    summaries: list[str] = []
    try:
        mutations_src = decoded.get("internal_mutations")
        summaries = await _execute_limye_mutations(db, org_id, mutations_src)
    except ValueError as exc:
        logger.warning("Mutation validation failed during configure: %s", exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "ui": ui_out,
        "mutations": summaries,
    }


class CustomComponentBody(BaseModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    props: dict[str, Any] = Field(default_factory=dict)
    target_sections: list[Any] = Field(default_factory=list)


@router.post("/ai/add-custom-component", status_code=status.HTTP_201_CREATED)
async def add_custom_component(
    body: CustomComponentBody,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_custom_component_table(db)
    oid = str(user["org_id"])
    dumped_props = json.dumps(body.props)
    dumped_sections = json.dumps(body.target_sections)
    row = await db.fetchrow(
        """
        INSERT INTO custom_component_definitions (
            org_id, name, component_type, props, target_sections
        ) VALUES (
            $1::uuid, $2, $3, $4::jsonb, $5::jsonb
        ) RETURNING *
        """,
        oid,
        body.name.strip(),
        body.type.strip(),
        dumped_props,
        dumped_sections,
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return record_to_api_dict(row)


@router.get("/org/custom-components")
async def list_custom_components(
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    await _ensure_custom_component_table(db)
    oid = str(user["org_id"])
    rows = await db.fetch(
        """
        SELECT * FROM custom_component_definitions
        WHERE org_id = $1::uuid
        ORDER BY created_at DESC
        """,
        oid,
    )
    return [record_to_api_dict(r) for r in rows]


__all__ = ["router"]
