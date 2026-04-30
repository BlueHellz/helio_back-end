"""Organization settings, custom fields, roles, pipelines, design mode, layouts."""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from helios_api.db.database import get_db, record_to_api_dict
from helios_api.middleware.auth import require_org_member

router = APIRouter(prefix="/org", tags=["settings"])

FREE_TIER_MAX_CUSTOM_ROLES = 3

FieldType = Literal[
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
]


async def _org(db: asyncpg.Connection, org_id: str) -> dict[str, Any]:
    r = await db.fetchrow("SELECT * FROM orgs WHERE id = $1::uuid LIMIT 1", org_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return record_to_api_dict(r)


@router.get("")
async def get_org(
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    return await _org(db, str(user["org_id"]))


class OrgUpdate(BaseModel):
    name: str = Field(min_length=1)


@router.put("")
async def put_org(
    body: OrgUpdate,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    await db.execute("UPDATE orgs SET name = $2 WHERE id = $1::uuid", oid, body.name)
    return await _org(db, oid)


@router.get("/custom-fields")
async def list_custom_fields(
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    rows = await db.fetch(
        "SELECT * FROM custom_field_definitions WHERE org_id = $1::uuid ORDER BY sort_order",
        oid,
    )
    return {"items": [record_to_api_dict(r) for r in rows]}


class CustomFieldCreate(BaseModel):
    name: str
    field_type: FieldType
    options: list[Any] = Field(default_factory=list)
    is_global: bool = False
    target_sections: list[Any] = Field(default_factory=list)
    visibility_rules: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    required: bool = False


@router.post("/custom-fields", status_code=status.HTTP_201_CREATED)
async def create_custom_field(
    body: CustomFieldCreate,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    d = body.model_dump()
    row = await db.fetchrow(
        """
        INSERT INTO custom_field_definitions (
            org_id, name, field_type, options, is_global, target_sections,
            visibility_rules, sort_order, required
        ) VALUES (
            $1::uuid, $2, $3, $4::jsonb, $5, $6::jsonb, $7::jsonb, $8, $9
        ) RETURNING *
        """,
        oid,
        d["name"],
        d["field_type"],
        json.dumps(d["options"]),
        d["is_global"],
        json.dumps(d["target_sections"]),
        json.dumps(d["visibility_rules"]),
        d["sort_order"],
        d["required"],
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return record_to_api_dict(row)


class CustomFieldUpdate(BaseModel):
    name: Optional[str] = None
    field_type: Optional[FieldType] = None
    options: Optional[list[Any]] = None
    is_global: Optional[bool] = None
    target_sections: Optional[list[Any]] = None
    visibility_rules: Optional[dict[str, Any]] = None
    sort_order: Optional[int] = None
    required: Optional[bool] = None


@router.put("/custom-fields/{field_id}")
async def update_custom_field(
    field_id: str,
    body: CustomFieldUpdate,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields")
    json_cols = {"options", "target_sections", "visibility_rules"}
    sets: list[str] = []
    args: list[Any] = [field_id, oid]
    i = 3
    for col, val in patch.items():
        if col in json_cols:
            sets.append(f"{col} = ${i}::jsonb")
            args.append(json.dumps(val))
        else:
            sets.append(f"{col} = ${i}")
            args.append(val)
        i += 1
    sql = f"""
        UPDATE custom_field_definitions SET {", ".join(sets)}
        WHERE id = $1::uuid AND org_id = $2::uuid
        RETURNING *
    """
    row = await db.fetchrow(sql, *args)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field not found")
    return record_to_api_dict(row)


@router.delete("/custom-fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_custom_field(
    field_id: str,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    oid = str(user["org_id"])
    await db.execute(
        "DELETE FROM custom_field_definitions WHERE id = $1::uuid AND org_id = $2::uuid",
        field_id,
        oid,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/roles")
async def list_org_roles(
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    rows = await db.fetch(
        "SELECT * FROM custom_roles WHERE org_id = $1::uuid",
        oid,
    )
    return {"items": [record_to_api_dict(r) for r in rows]}


class CustomRoleCreate(BaseModel):
    name: str = Field(min_length=1)
    permissions: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_org_role(
    body: CustomRoleCreate,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    n = await db.fetchval(
        "SELECT count(*) FROM custom_roles WHERE org_id = $1::uuid",
        oid,
    )
    if (n or 0) >= FREE_TIER_MAX_CUSTOM_ROLES:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Maximum of {FREE_TIER_MAX_CUSTOM_ROLES} custom roles on free tier",
        )
    row = await db.fetchrow(
        """
        INSERT INTO custom_roles (org_id, name, permissions, is_default)
        VALUES ($1::uuid, $2, $3::jsonb, $4)
        RETURNING *
        """,
        oid,
        body.name,
        json.dumps(body.permissions),
        body.is_default,
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return record_to_api_dict(row)


class CustomRoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[dict[str, Any]] = None
    is_default: Optional[bool] = None


@router.put("/roles/{role_id}")
async def update_org_role(
    role_id: str,
    body: CustomRoleUpdate,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields")
    sets: list[str] = []
    args: list[Any] = [role_id, oid]
    i = 3
    for col, val in patch.items():
        if col == "permissions":
            sets.append(f"{col} = ${i}::jsonb")
            args.append(json.dumps(val))
        else:
            sets.append(f"{col} = ${i}")
            args.append(val)
        i += 1
    row = await db.fetchrow(
        f"UPDATE custom_roles SET {', '.join(sets)} WHERE id = $1::uuid AND org_id = $2::uuid RETURNING *",
        *args,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    return record_to_api_dict(row)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_org_role(
    role_id: str,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    oid = str(user["org_id"])
    await db.execute(
        "DELETE FROM custom_roles WHERE id = $1::uuid AND org_id = $2::uuid",
        role_id,
        oid,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{assign_user_id}/assign-role", status_code=status.HTTP_201_CREATED)
async def assign_user_role(
    assign_user_id: str,
    role_id: str = Query(..., description="custom_roles.id"),
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    cr = await db.fetchrow(
        "SELECT id FROM custom_roles WHERE id = $1::uuid AND org_id = $2::uuid LIMIT 1",
        role_id,
        oid,
    )
    if cr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not in this org")
    await db.execute(
        """
        INSERT INTO user_roles (user_id, role_id) VALUES ($1::uuid, $2::uuid)
        ON CONFLICT (user_id, role_id) DO NOTHING
        """,
        assign_user_id,
        role_id,
    )
    return {"user_id": assign_user_id, "role_id": role_id}


@router.delete(
    "/users/{assign_user_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_user_role(
    assign_user_id: str,
    role_id: str,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    oid = str(user["org_id"])
    cr = await db.fetchrow(
        "SELECT id FROM custom_roles WHERE id = $1::uuid AND org_id = $2::uuid LIMIT 1",
        role_id,
        oid,
    )
    if cr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not in this org")
    await db.execute(
        "DELETE FROM user_roles WHERE user_id = $1::uuid AND role_id = $2::uuid",
        assign_user_id,
        role_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/pipelines")
async def list_pipelines(
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    rows = await db.fetch(
        "SELECT * FROM pipelines WHERE org_id = $1::uuid",
        oid,
    )
    return {"items": [record_to_api_dict(r) for r in rows]}


class StageIn(BaseModel):
    name: str
    order_index: int
    color: str = "#0066FF"


class PipelineCreate(BaseModel):
    name: str = Field(min_length=1)
    stages: list[StageIn] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_pipeline_name(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("stages", mode="before")
    @classmethod
    def _none_or_missing_stages_to_empty(cls, v: Any) -> Any:
        if v is None:
            return []
        return v


@router.post("/pipelines", status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    body: PipelineCreate,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    async with db.transaction():
        row = await db.fetchrow(
            "INSERT INTO pipelines (org_id, name) VALUES ($1::uuid, $2) RETURNING *",
            oid,
            body.name,
        )
        if row is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Pipeline insert failed")
        pid = str(row["id"])
        for st in body.stages:
            await db.execute(
                """
                INSERT INTO pipeline_stages (pipeline_id, name, order_index, color)
                VALUES ($1::uuid, $2, $3, $4)
                """,
                pid,
                st.name,
                st.order_index,
                st.color,
            )
        stage_rows = await db.fetch(
            """
            SELECT * FROM pipeline_stages
            WHERE pipeline_id = $1::uuid
            ORDER BY order_index, id
            """,
            pid,
        )

    out = record_to_api_dict(row)
    out["stages"] = [record_to_api_dict(s) for s in stage_rows]
    return out


class PipelineUpdate(BaseModel):
    name: Optional[str] = None


@router.put("/pipelines/{pipeline_id}")
async def update_pipeline(
    pipeline_id: str,
    body: PipelineUpdate,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields")
    row = await db.fetchrow(
        "UPDATE pipelines SET name = $3 WHERE id = $1::uuid AND org_id = $2::uuid RETURNING *",
        pipeline_id,
        oid,
        patch["name"],
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    return record_to_api_dict(row)


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_pipeline(
    pipeline_id: str,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    oid = str(user["org_id"])
    await db.execute(
        "DELETE FROM pipelines WHERE id = $1::uuid AND org_id = $2::uuid",
        pipeline_id,
        oid,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/pipelines/{pipeline_id}/stages")
async def list_stages(
    pipeline_id: str,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    pl = await db.fetchrow(
        "SELECT id FROM pipelines WHERE id = $1::uuid AND org_id = $2::uuid LIMIT 1",
        pipeline_id,
        oid,
    )
    if pl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    rows = await db.fetch(
        "SELECT * FROM pipeline_stages WHERE pipeline_id = $1::uuid ORDER BY order_index",
        pipeline_id,
    )
    return {"items": [record_to_api_dict(r) for r in rows]}


@router.post("/pipelines/{pipeline_id}/stages", status_code=status.HTTP_201_CREATED)
async def add_stage(
    pipeline_id: str,
    body: StageIn,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    pl = await db.fetchrow(
        "SELECT id FROM pipelines WHERE id = $1::uuid AND org_id = $2::uuid LIMIT 1",
        pipeline_id,
        oid,
    )
    if pl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    row = await db.fetchrow(
        """
        INSERT INTO pipeline_stages (pipeline_id, name, order_index, color)
        VALUES ($1::uuid, $2, $3, $4)
        RETURNING *
        """,
        pipeline_id,
        body.name,
        body.order_index,
        body.color,
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return record_to_api_dict(row)


@router.put("/pipelines/{pipeline_id}/stages/{stage_id}")
async def update_stage(
    pipeline_id: str,
    stage_id: str,
    body: StageIn,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    pl = await db.fetchrow(
        "SELECT id FROM pipelines WHERE id = $1::uuid AND org_id = $2::uuid LIMIT 1",
        pipeline_id,
        oid,
    )
    if pl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    row = await db.fetchrow(
        """
        UPDATE pipeline_stages
        SET name = $3, order_index = $4, color = $5
        WHERE id = $1::uuid AND pipeline_id = $2::uuid
        RETURNING *
        """,
        stage_id,
        pipeline_id,
        body.name,
        body.order_index,
        body.color,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stage not found")
    return record_to_api_dict(row)


@router.delete(
    "/pipelines/{pipeline_id}/stages/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_stage(
    pipeline_id: str,
    stage_id: str,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    oid = str(user["org_id"])
    pl = await db.fetchrow(
        "SELECT id FROM pipelines WHERE id = $1::uuid AND org_id = $2::uuid LIMIT 1",
        pipeline_id,
        oid,
    )
    if pl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    await db.execute(
        "DELETE FROM pipeline_stages WHERE id = $1::uuid AND pipeline_id = $2::uuid",
        stage_id,
        pipeline_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/design-mode")
async def get_design_mode(
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, bool]:
    oid = str(user["org_id"])
    o = await _org(db, oid)
    return {"design_mode": bool(o.get("design_mode", False))}


class DesignModeBody(BaseModel):
    design_mode: bool


@router.put("/design-mode")
async def put_design_mode(
    body: DesignModeBody,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, bool]:
    oid = str(user["org_id"])
    await db.execute(
        "UPDATE orgs SET design_mode = $2 WHERE id = $1::uuid",
        oid,
        body.design_mode,
    )
    return {"design_mode": body.design_mode}


@router.post("/layout/{section}")
async def save_layout(
    section: str,
    body: dict[str, Any],
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    await db.execute(
        """
        INSERT INTO org_layouts (org_id, section, layout, updated_at)
        VALUES ($1::uuid, $2, $3::jsonb, now())
        ON CONFLICT (org_id, section) DO UPDATE SET
            layout = EXCLUDED.layout,
            updated_at = now()
        """,
        oid,
        section,
        json.dumps(body),
    )
    return {"org_id": oid, "section": section, "saved": True}


@router.get("/layout/{section}")
async def get_layout(
    section: str,
    user: dict = Depends(require_org_member),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    r = await db.fetchrow(
        """
        SELECT layout FROM org_layouts
        WHERE org_id = $1::uuid AND section = $2 LIMIT 1
        """,
        oid,
        section,
    )
    if r is None:
        return {"layout": {}}
    lay = r["layout"]
    if isinstance(lay, str):
        lay = json.loads(lay)
    return {"layout": lay or {}}
