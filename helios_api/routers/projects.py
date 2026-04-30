"""Solar project CRUD."""

from __future__ import annotations

from typing import Any, Literal, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from helios_api.db.database import get_db, record_to_api_dict
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
async def list_projects(
    status_f: Optional[str] = Query(None, alias="status"),
    project_type: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    uid = user["id"]
    oid = _org_id_for_user(user)
    args: list[Any] = []
    if oid:
        where = "(user_id = $1::uuid OR org_id = $2::uuid)"
        args = [uid, oid]
        n = 3
    else:
        where = "user_id = $1::uuid"
        args = [uid]
        n = 2
    if status_f:
        where += f" AND status = ${n}"
        args.append(status_f)
        n += 1
    if project_type:
        where += f" AND project_type = ${n}"
        args.append(project_type)
    q = f"SELECT * FROM projects WHERE {where} ORDER BY created_at DESC"
    rows = await db.fetch(q, *args)
    return {"items": [record_to_api_dict(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    oid = _org_id_for_user(user)
    row = await db.fetchrow(
        """
        INSERT INTO projects (user_id, org_id, address, project_type, custom_data)
        VALUES ($1::uuid, $2, $3, $4, $5::jsonb)
        RETURNING *
        """,
        user["id"],
        oid,
        body.address,
        body.project_type,
        body.custom_data,
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return record_to_api_dict(row)


async def _can_access_project(
    db: asyncpg.Connection, project_id: str, user: dict
) -> Optional[dict[str, Any]]:
    r = await db.fetchrow("SELECT * FROM projects WHERE id = $1::uuid LIMIT 1", project_id)
    if r is None:
        return None
    row = record_to_api_dict(r)
    if str(row["user_id"]) == str(user["id"]):
        return row
    oid = _org_id_for_user(user)
    if oid and row.get("org_id") and str(row["org_id"]) == oid:
        return row
    return None


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    row = await _can_access_project(db, project_id, user)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return row


@router.put("/{project_id}")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    base = await _can_access_project(db, project_id, user)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No updates")
    if "custom_data" in patch and patch["custom_data"] is not None:
        merged = {**(base.get("custom_data") or {}), **patch["custom_data"]}
        patch["custom_data"] = merged
    json_cols = {
        "roof_data",
        "panel_layout",
        "electrical_spec",
        "financial_summary",
        "custom_data",
    }
    sets: list[str] = []
    args: list[Any] = []
    i = 1
    for col, val in patch.items():
        if col in json_cols:
            sets.append(f"{col} = ${i}::jsonb")
        else:
            sets.append(f"{col} = ${i}")
        args.append(val)
        i += 1
    args.append(project_id)
    sql = f"UPDATE projects SET {', '.join(sets)} WHERE id = ${i}::uuid RETURNING *"
    row = await db.fetchrow(sql, *args)
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Update failed")
    return record_to_api_dict(row)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_project(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    base = await _can_access_project(db, project_id, user)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if str(base["user_id"]) != str(user["id"]) and user.get("role") not in ("installer", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owner or org staff can delete")
    await db.execute("DELETE FROM projects WHERE id = $1::uuid", project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
