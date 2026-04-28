"""Solar project CRUD."""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from supabase import Client

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_user

router = APIRouter(prefix="/projects", tags=["projects"])

ProjType = Literal["residential", "commercial", "industrial"]
ProjStatus = Literal[
    "draft",
    "designed",
    "drone_requested",
    "drone_completed",
    "permit_submitted",
    "permitted",
    "installed",
    "inspected",
    "completed",
]


class ProjectCreate(BaseModel):
    address: str = Field(min_length=1)
    project_type: ProjType = "residential"
    custom_data: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    address: Optional[str] = None
    project_type: Optional[ProjType] = None
    roof_data: Optional[dict[str, Any]] = None
    panel_layout: Optional[dict[str, Any]] = None
    electrical_spec: Optional[dict[str, Any]] = None
    financial_summary: Optional[dict[str, Any]] = None
    custom_data: Optional[dict[str, Any]] = None
    status: Optional[ProjStatus] = None


def _org_id_for_user(user: dict) -> Optional[str]:
    return str(user["org_id"]) if user.get("org_id") else None


@router.get("")
def list_projects(
    status_f: Optional[str] = Query(None, alias="status"),
    project_type: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    uid = user["id"]
    oid = _org_id_for_user(user)
    q = supabase.table("projects").select("*")
    if oid:
        q = q.or_(f"user_id.eq.{uid},org_id.eq.{oid}")
    else:
        q = q.eq("user_id", uid)
    if status_f:
        q = q.eq("status", status_f)
    if project_type:
        q = q.eq("project_type", project_type)
    r = q.order("created_at", desc=True).execute()
    return {"items": r.data or []}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    oid = _org_id_for_user(user)
    row = {
        "user_id": user["id"],
        "org_id": oid,
        "address": body.address,
        "project_type": body.project_type,
        "custom_data": body.custom_data,
    }
    ins = supabase.table("projects").insert(row).execute()
    if not ins.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return dict(ins.data[0])


def _can_access_project(supabase: Client, project_id: str, user: dict) -> Optional[dict[str, Any]]:
    r = supabase.table("projects").select("*").eq("id", project_id).limit(1).execute()
    if not r.data:
        return None
    row = dict(r.data[0])
    if row["user_id"] == user["id"]:
        return row
    oid = _org_id_for_user(user)
    if oid and row.get("org_id") == oid:
        return row
    return None


@router.get("/{project_id}")
def get_project(
    project_id: str,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    row = _can_access_project(supabase, project_id, user)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return row


@router.put("/{project_id}")
def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    base = _can_access_project(supabase, project_id, user)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No updates")
    if "custom_data" in patch and patch["custom_data"] is not None:
        merged = {**(base.get("custom_data") or {}), **patch["custom_data"]}
        patch["custom_data"] = merged
    r = supabase.table("projects").update(patch).eq("id", project_id).execute()
    if not r.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Update failed")
    return dict(r.data[0])


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_project(
    project_id: str,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> Response:
    base = _can_access_project(supabase, project_id, user)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if base["user_id"] != user["id"] and user.get("role") not in ("installer", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owner or org staff can delete")
    supabase.table("projects").delete().eq("id", project_id).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
