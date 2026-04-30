"""Drone operator job queue (MVP CRUD)."""

from __future__ import annotations

from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from helios_api.db.database import get_db, record_to_api_dict
from helios_api.middleware.auth import get_current_drone_op, get_current_user

router = APIRouter(prefix="/drone", tags=["drone"])


@router.get("/jobs")
async def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: asyncpg.Connection = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    if status_filter:
        rows = await db.fetch(
            """
            SELECT * FROM scan_jobs WHERE status = $1
            ORDER BY created_at DESC LIMIT 100
            """,
            status_filter,
        )
    else:
        rows = await db.fetch(
            "SELECT * FROM scan_jobs ORDER BY created_at DESC LIMIT 100"
        )
    return {"items": [record_to_api_dict(r) for r in rows]}


@router.post("/jobs/{job_id}/accept")
async def accept_job(
    job_id: str,
    user: dict = Depends(get_current_drone_op),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    row = await db.fetchrow(
        """
        UPDATE scan_jobs
        SET drone_op_id = $2::uuid, status = $3
        WHERE id = $1::uuid AND status = $4
        RETURNING *
        """,
        job_id,
        user["id"],
        "accepted",
        "pending",
    )
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job not available")
    return record_to_api_dict(row)


class UploadBody(BaseModel):
    video_upload_path: str = Field(min_length=4)


@router.post("/jobs/{job_id}/upload")
async def upload_video(
    job_id: str,
    body: UploadBody,
    user: dict = Depends(get_current_drone_op),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    job = await db.fetchrow("SELECT * FROM scan_jobs WHERE id = $1::uuid LIMIT 1", job_id)
    if job is None or str(job["drone_op_id"] or "") != str(user["id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    row = await db.fetchrow(
        """
        UPDATE scan_jobs
        SET video_upload_path = $2, status = $3
        WHERE id = $1::uuid
        RETURNING *
        """,
        job_id,
        body.video_upload_path,
        "scan_uploaded",
    )
    return record_to_api_dict(row) if row else {"ok": True}


@router.post("/jobs/{job_id}/complete")
async def complete_job(
    job_id: str,
    user: dict = Depends(get_current_drone_op),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    job = await db.fetchrow("SELECT * FROM scan_jobs WHERE id = $1::uuid LIMIT 1", job_id)
    if job is None or str(job["drone_op_id"] or "") != str(user["id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    row = await db.fetchrow(
        """
        UPDATE scan_jobs SET status = $2 WHERE id = $1::uuid
        RETURNING *
        """,
        job_id,
        "installed",
    )
    return record_to_api_dict(row) if row else {"ok": True}


@router.get("/earnings")
async def earnings(
    user: dict = Depends(get_current_drone_op),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    rows = await db.fetch(
        "SELECT payment_total_hlio FROM scan_jobs WHERE drone_op_id = $1::uuid",
        user["id"],
    )
    total = sum(float(r["payment_total_hlio"] or 0) for r in rows)
    return {"total_hlio": total, "job_count": len(rows)}
