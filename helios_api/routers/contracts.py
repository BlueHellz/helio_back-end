"""Contract file handling (stubs)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from helios_api.db.database import get_db, record_to_api_dict
from helios_api.middleware.auth import get_current_user
from helios_api.routers.projects import _can_access_project

router = APIRouter(prefix="/contracts", tags=["contracts"])


class SignBody(BaseModel):
    signature_data: str


@router.post("/{project_id}/upload")
async def upload_contract(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if await _can_access_project(db, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    url = f"stub://storage/contracts/{project_id}/{file.filename}"
    row = await db.fetchrow(
        """
        INSERT INTO contracts (project_id, file_url, status)
        VALUES ($1::uuid, $2, $3)
        RETURNING *
        """,
        project_id,
        url,
        "uploaded",
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Insert failed")
    return {
        "contract": record_to_api_dict(row),
        "note": "Wire object storage upload in production.",
    }


@router.post("/{project_id}/sign")
async def sign_contract(
    project_id: str,
    body: SignBody,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    if await _can_access_project(db, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    signed_at = datetime.now(timezone.utc)
    await db.execute(
        """
        UPDATE contracts
        SET signature_data = $2, signed_at = $3, status = $4
        WHERE project_id = $1::uuid
        """,
        project_id,
        body.signature_data,
        signed_at,
        "signed",
    )
    return {"ok": True, "project_id": project_id}


@router.get("/{project_id}/download")
async def download_contract(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    if await _can_access_project(db, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    r = await db.fetchrow(
        "SELECT * FROM contracts WHERE project_id = $1::uuid LIMIT 1",
        project_id,
    )
    if r is None:
        return {"file_url": None}
    return {"file_url": record_to_api_dict(r).get("file_url")}
