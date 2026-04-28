"""Organization settings, custom fields, roles, pipelines, design mode, layouts."""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from supabase import Client

from helios_api.db.supabase import get_supabase
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


def _org(supabase: Client, org_id: str) -> dict[str, Any]:
    r = supabase.table("orgs").select("*").eq("id", org_id).limit(1).execute()
    if not r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return dict(r.data[0])


@router.get("")
def get_org(
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    return _org(supabase, str(user["org_id"]))


class OrgUpdate(BaseModel):
    name: str = Field(min_length=1)


@router.put("")
def put_org(
    body: OrgUpdate,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    supabase.table("orgs").update({"name": body.name}).eq("id", oid).execute()
    return _org(supabase, oid)


@router.get("/custom-fields")
def list_custom_fields(
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    r = (
        supabase.table("custom_field_definitions")
        .select("*")
        .eq("org_id", oid)
        .order("sort_order")
        .execute()
    )
    return {"items": r.data or []}


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
def create_custom_field(
    body: CustomFieldCreate,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    row = {**body.model_dump(), "org_id": oid}
    ins = supabase.table("custom_field_definitions").insert(row).execute()
    if not ins.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return dict(ins.data[0])


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
def update_custom_field(
    field_id: str,
    body: CustomFieldUpdate,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields")
    r = (
        supabase.table("custom_field_definitions")
        .update(patch)
        .eq("id", field_id)
        .eq("org_id", oid)
        .execute()
    )
    if not r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field not found")
    return dict(r.data[0])


@router.delete("/custom-fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_custom_field(
    field_id: str,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> Response:
    oid = str(user["org_id"])
    supabase.table("custom_field_definitions").delete().eq("id", field_id).eq("org_id", oid).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/roles")
def list_org_roles(
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    r = supabase.table("custom_roles").select("*").eq("org_id", oid).execute()
    return {"items": r.data or []}


class CustomRoleCreate(BaseModel):
    name: str = Field(min_length=1)
    permissions: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_org_role(
    body: CustomRoleCreate,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    existing = supabase.table("custom_roles").select("id").eq("org_id", oid).execute()
    n = len(existing.data or [])
    if n >= FREE_TIER_MAX_CUSTOM_ROLES:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Maximum of {FREE_TIER_MAX_CUSTOM_ROLES} custom roles on free tier",
        )
    ins = (
        supabase.table("custom_roles")
        .insert(
            {
                "org_id": oid,
                "name": body.name,
                "permissions": body.permissions,
                "is_default": body.is_default,
            }
        )
        .execute()
    )
    if not ins.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return dict(ins.data[0])


class CustomRoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[dict[str, Any]] = None
    is_default: Optional[bool] = None


@router.put("/roles/{role_id}")
def update_org_role(
    role_id: str,
    body: CustomRoleUpdate,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    r = (
        supabase.table("custom_roles")
        .update(patch)
        .eq("id", role_id)
        .eq("org_id", oid)
        .execute()
    )
    if not r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    return dict(r.data[0])


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_org_role(
    role_id: str,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> Response:
    oid = str(user["org_id"])
    supabase.table("custom_roles").delete().eq("id", role_id).eq("org_id", oid).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{assign_user_id}/assign-role", status_code=status.HTTP_201_CREATED)
def assign_user_role(
    assign_user_id: str,
    role_id: str = Query(..., description="custom_roles.id"),
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    cr = (
        supabase.table("custom_roles")
        .select("id")
        .eq("id", role_id)
        .eq("org_id", oid)
        .limit(1)
        .execute()
    )
    if not cr.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not in this org")
    supabase.table("user_roles").insert({"user_id": assign_user_id, "role_id": role_id}).execute()
    return {"user_id": assign_user_id, "role_id": role_id}


@router.delete(
    "/users/{assign_user_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_user_role(
    assign_user_id: str,
    role_id: str,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> Response:
    oid = str(user["org_id"])
    cr = (
        supabase.table("custom_roles")
        .select("id")
        .eq("id", role_id)
        .eq("org_id", oid)
        .limit(1)
        .execute()
    )
    if not cr.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not in this org")
    supabase.table("user_roles").delete().eq("user_id", assign_user_id).eq(
        "role_id", role_id
    ).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/pipelines")
def list_pipelines(
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    r = supabase.table("pipelines").select("*").eq("org_id", oid).execute()
    return {"items": r.data or []}


class StageIn(BaseModel):
    name: str
    order_index: int
    color: str = "#0066FF"


class PipelineCreate(BaseModel):
    name: str
    stages: list[StageIn] = Field(default_factory=list)


@router.post("/pipelines", status_code=status.HTTP_201_CREATED)
def create_pipeline(
    body: PipelineCreate,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    ins = supabase.table("pipelines").insert({"org_id": oid, "name": body.name}).execute()
    if not ins.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Pipeline insert failed")
    pid = str(ins.data[0]["id"])
    for st in body.stages:
        supabase.table("pipeline_stages").insert(
            {
                "pipeline_id": pid,
                "name": st.name,
                "order_index": st.order_index,
                "color": st.color,
            }
        ).execute()
    return {"id": pid, "name": body.name, "stages": body.stages}


class PipelineUpdate(BaseModel):
    name: Optional[str] = None


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(
    pipeline_id: str,
    body: PipelineUpdate,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields")
    r = (
        supabase.table("pipelines")
        .update(patch)
        .eq("id", pipeline_id)
        .eq("org_id", oid)
        .execute()
    )
    if not r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    return dict(r.data[0])


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_pipeline(
    pipeline_id: str,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> Response:
    oid = str(user["org_id"])
    supabase.table("pipelines").delete().eq("id", pipeline_id).eq("org_id", oid).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/pipelines/{pipeline_id}/stages")
def list_stages(
    pipeline_id: str,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    pl = (
        supabase.table("pipelines")
        .select("id")
        .eq("id", pipeline_id)
        .eq("org_id", oid)
        .limit(1)
        .execute()
    )
    if not pl.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    r = (
        supabase.table("pipeline_stages")
        .select("*")
        .eq("pipeline_id", pipeline_id)
        .order("order_index")
        .execute()
    )
    return {"items": r.data or []}


@router.post("/pipelines/{pipeline_id}/stages", status_code=status.HTTP_201_CREATED)
def add_stage(
    pipeline_id: str,
    body: StageIn,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    pl = (
        supabase.table("pipelines")
        .select("id")
        .eq("id", pipeline_id)
        .eq("org_id", oid)
        .limit(1)
        .execute()
    )
    if not pl.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    ins = (
        supabase.table("pipeline_stages")
        .insert(
            {
                "pipeline_id": pipeline_id,
                "name": body.name,
                "order_index": body.order_index,
                "color": body.color,
            }
        )
        .execute()
    )
    if not ins.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return dict(ins.data[0])


@router.put("/pipelines/{pipeline_id}/stages/{stage_id}")
def update_stage(
    pipeline_id: str,
    stage_id: str,
    body: StageIn,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    pl = (
        supabase.table("pipelines")
        .select("id")
        .eq("id", pipeline_id)
        .eq("org_id", oid)
        .limit(1)
        .execute()
    )
    if not pl.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    r = (
        supabase.table("pipeline_stages")
        .update({"name": body.name, "order_index": body.order_index, "color": body.color})
        .eq("id", stage_id)
        .eq("pipeline_id", pipeline_id)
        .execute()
    )
    if not r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stage not found")
    return dict(r.data[0])


@router.delete(
    "/pipelines/{pipeline_id}/stages/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_stage(
    pipeline_id: str,
    stage_id: str,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> Response:
    oid = str(user["org_id"])
    pl = (
        supabase.table("pipelines")
        .select("id")
        .eq("id", pipeline_id)
        .eq("org_id", oid)
        .limit(1)
        .execute()
    )
    if not pl.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    supabase.table("pipeline_stages").delete().eq("id", stage_id).eq(
        "pipeline_id", pipeline_id
    ).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/design-mode")
def get_design_mode(
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, bool]:
    oid = str(user["org_id"])
    o = _org(supabase, oid)
    return {"design_mode": bool(o.get("design_mode", False))}


class DesignModeBody(BaseModel):
    design_mode: bool


@router.put("/design-mode")
def put_design_mode(
    body: DesignModeBody,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, bool]:
    oid = str(user["org_id"])
    supabase.table("orgs").update({"design_mode": body.design_mode}).eq("id", oid).execute()
    return {"design_mode": body.design_mode}


@router.post("/layout/{section}")
def save_layout(
    section: str,
    body: dict[str, Any],
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    supabase.table("org_layouts").upsert(
        {"org_id": oid, "section": section, "layout": body}, on_conflict="org_id,section"
    ).execute()
    return {"org_id": oid, "section": section, "saved": True}


@router.get("/layout/{section}")
def get_layout(
    section: str,
    user: dict = Depends(require_org_member),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = str(user["org_id"])
    r = (
        supabase.table("org_layouts")
        .select("*")
        .eq("org_id", oid)
        .eq("section", section)
        .limit(1)
        .execute()
    )
    if not r.data:
        return {"layout": {}}
    return {"layout": r.data[0].get("layout", {})}
