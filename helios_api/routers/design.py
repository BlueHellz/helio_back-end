"""Design pipeline trigger (stub)."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from helios_api.db.database import get_db
from helios_api.middleware.auth import get_current_user
from helios_api.routers.projects import _can_access_project

router = APIRouter(prefix="/design", tags=["design"])


@router.post("/{project_id}")
async def run_design_pipeline(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    if await _can_access_project(db, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return {
        "ok": True,
        "project_id": project_id,
        "message": (
            "Design pipeline stub — full run will orchestrate "
            "Google Solar API → layout tools → NEC → financial model."
        ),
        "steps": ["google_solar", "layout_engine", "nec_check", "proposal_pdf"],
    }
