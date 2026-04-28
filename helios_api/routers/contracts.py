"""Contract file handling (stubs)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from supabase import Client

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_user
from helios_api.routers.projects import _can_access_project

router = APIRouter(prefix="/contracts", tags=["contracts"])


class SignBody(BaseModel):
    signature_data: str


@router.post("/{project_id}/upload")
async def upload_contract(
    project_id: str,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if _can_access_project(supabase, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    url = f"stub://storage/contracts/{project_id}/{file.filename}"
    ins = (
        supabase.table("contracts")
        .insert({"project_id": project_id, "file_url": url, "status": "uploaded"})
        .execute()
    )
    if not ins.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return {"contract": ins.data[0], "note": "Wire Supabase Storage upload in production."}


@router.post("/{project_id}/sign")
def sign_contract(
    project_id: str,
    body: SignBody,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    if _can_access_project(supabase, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    supabase.table("contracts").update(
        {
            "signature_data": body.signature_data,
            "signed_at": datetime.now(timezone.utc).isoformat(),
            "status": "signed",
        }
    ).eq("project_id", project_id).execute()
    return {"ok": True, "project_id": project_id}


@router.get("/{project_id}/download")
def download_contract(
    project_id: str,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    if _can_access_project(supabase, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    r = (
        supabase.table("contracts")
        .select("*")
        .eq("project_id", project_id)
        .limit(1)
        .execute()
    )
    if not r.data:
        return {"file_url": None}
    # table has no created_at in schema — order by id is ok
    return {"file_url": r.data[0].get("file_url")}
