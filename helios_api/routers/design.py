"""Design pipeline trigger (stub)."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from helios_api.db.database import get_db
from helios_api.routers.projects import fetch_project_by_id

router = APIRouter(prefix="/design", tags=["design"])


@router.post("/{project_id}")
async def run_design_pipeline(
    project_id: str,
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    if await fetch_project_by_id(db, project_id) is None:
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
