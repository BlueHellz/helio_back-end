"""Drone operator job queue (MVP CRUD)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from supabase import Client

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_drone_op, get_current_user

router = APIRouter(prefix="/drone", tags=["drone"])


@router.get("/jobs")
def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    supabase: Client = Depends(get_supabase),
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """List scan jobs — drone ops see actionable queue; everyone else sees recent rows."""
    q = supabase.table("scan_jobs").select("*")
    if status_filter:
        q = q.eq("status", status_filter)
    r = q.order("created_at", desc=True).limit(100).execute()
    return {"items": r.data or []}


@router.post("/jobs/{job_id}/accept")
def accept_job(
    job_id: str,
    user: dict = Depends(get_current_drone_op),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    r = (
        supabase.table("scan_jobs")
        .update({"drone_op_id": user["id"], "status": "accepted"})
        .eq("id", job_id)
        .eq("status", "pending")
        .execute()
    )
    if not r.data:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job not available")
    return dict(r.data[0])


class UploadBody(BaseModel):
    video_upload_path: str = Field(min_length=4)


@router.post("/jobs/{job_id}/upload")
def upload_video(
    job_id: str,
    body: UploadBody,
    user: dict = Depends(get_current_drone_op),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    job = supabase.table("scan_jobs").select("*").eq("id", job_id).limit(1).execute()
    if not job.data or job.data[0].get("drone_op_id") != user["id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    r = (
        supabase.table("scan_jobs")
        .update({"video_upload_path": body.video_upload_path, "status": "scan_uploaded"})
        .eq("id", job_id)
        .execute()
    )
    return dict(r.data[0]) if r.data else {"ok": True}


@router.post("/jobs/{job_id}/complete")
def complete_job(
    job_id: str,
    user: dict = Depends(get_current_drone_op),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    job = supabase.table("scan_jobs").select("*").eq("id", job_id).limit(1).execute()
    if not job.data or job.data[0].get("drone_op_id") != user["id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    r = (
        supabase.table("scan_jobs")
        .update({"status": "installed"})
        .eq("id", job_id)
        .execute()
    )
    return dict(r.data[0]) if r.data else {"ok": True}


@router.get("/earnings")
def earnings(
    user: dict = Depends(get_current_drone_op),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    r = (
        supabase.table("scan_jobs")
        .select("payment_total_hlio")
        .eq("drone_op_id", user["id"])
        .execute()
    )
    total = sum(float(row.get("payment_total_hlio") or 0) for row in (r.data or []))
    return {"total_hlio": total, "job_count": len(r.data or [])}
