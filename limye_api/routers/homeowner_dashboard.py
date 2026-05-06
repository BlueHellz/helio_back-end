"""Homeowner dashboard: installers, funders, inspection, timeline, documents, messages."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from limye_api.db.database import get_db, record_to_api_dict
from limye_api.middleware.auth import get_current_homeowner
from limye_api.routers.projects import _can_access_project

router = APIRouter(tags=["homeowner-dashboard"])

MOCK_INSTALLERS: list[dict[str, Any]] = [
    {
        "id": "ins-mvp-sunrise",
        "name": "Sunrise Solar Co.",
        "rating": 4.8,
        "license": "HI-ELEC-10492",
        "contact": {"email": "hello@sunrisesolar.example", "phone": "+1-808-555-0101"},
        "terms": "Net 30 after install; 10-year workmanship warranty.",
    },
    {
        "id": "ins-mvp-pacific",
        "name": "Pacific PV Partners",
        "rating": 4.6,
        "license": "HI-CON-88301",
        "contact": {"email": "projects@pacificpv.example", "phone": "+1-808-555-0102"},
        "terms": "Milestone billing; NABCEP-certified crew; 5-year roof penetration warranty.",
    },
]

MOCK_FUNDERS: list[dict[str, Any]] = [
    {
        "id": "funder-community-pool",
        "name": "LIMYÈ Community Pool",
        "type": "community_pool",
        "terms": {
            "rateApr": 5.25,
            "termYears": 15,
            "notes": "Crowdfunded tranches; early payoff without penalty after year 3.",
        },
    },
    {
        "id": "funder-green-bank",
        "name": "Hawaiʻi Green Bank (demo)",
        "type": "green_bank",
        "terms": {
            "rateApr": 4.9,
            "termYears": 20,
            "notes": "Income-qualified rebates may stack; subject to credit approval.",
        },
    },
]

MOCK_DOCUMENTS: list[dict[str, str]] = [
    {
        "name": "Site assessment summary",
        "url": "https://example.com/limye/placeholder/site-assessment.pdf",
    },
    {
        "name": "Utility interconnection application",
        "url": "https://example.com/limye/placeholder/interconnection.pdf",
    },
    {
        "name": "Proposal overview",
        "url": "https://example.com/limye/placeholder/proposal-overview.pdf",
    },
]

_INSTALLER_BY_ID = {i["id"]: i for i in MOCK_INSTALLERS}
_FUNDER_BY_ID = {f["id"]: f for f in MOCK_FUNDERS}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inspection_slot_datetimes() -> list[str]:
    """Mock slots: next several weekdays at 9:00 and 13:00 UTC."""
    out: list[str] = []
    d = date.today()
    while len(out) < 16:
        if d.weekday() < 5:
            for hour in (9, 13):
                dt = datetime(d.year, d.month, d.day, hour, 0, 0, tzinfo=timezone.utc)
                out.append(dt.isoformat())
        d += timedelta(days=1)
    return out


def _timeline_patch_json(description: str) -> str:
    payload = [{"date": _utc_now_iso(), "description": description}]
    return json.dumps(payload)


class SelectInstallerBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    installer_id: str = Field(alias="installerId")


class SelectFunderBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    funder_id: str = Field(alias="funderId")


class BookInspectionBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slot_datetime: datetime = Field(alias="datetime")


class MessageCreateBody(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


@router.get("/installers")
async def list_installers(_user: dict = Depends(get_current_homeowner)) -> dict[str, Any]:
    return {"items": MOCK_INSTALLERS}


@router.get("/funders")
async def list_funders(_user: dict = Depends(get_current_homeowner)) -> dict[str, Any]:
    return {"items": MOCK_FUNDERS}


@router.post("/projects/{project_id}/select-installer")
async def select_installer(
    project_id: str,
    body: SelectInstallerBody,
    user: dict = Depends(get_current_homeowner),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    if body.installer_id not in _INSTALLER_BY_ID:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown installerId")
    base = await _can_access_project(db, project_id, user)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    name = _INSTALLER_BY_ID[body.installer_id]["name"]
    desc = f"Installer selected: {name}"
    row = await db.fetchrow(
        """
        UPDATE projects
        SET selected_installer_id = $2,
            timeline_events = COALESCE(timeline_events, '[]'::jsonb) || $3::jsonb,
            updated_at = now()
        WHERE id = $1::uuid
        RETURNING *
        """,
        project_id,
        body.installer_id,
        _timeline_patch_json(desc),
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Update failed")
    return record_to_api_dict(row)


@router.post("/projects/{project_id}/select-funder")
async def select_funder(
    project_id: str,
    body: SelectFunderBody,
    user: dict = Depends(get_current_homeowner),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    if body.funder_id not in _FUNDER_BY_ID:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown funderId")
    base = await _can_access_project(db, project_id, user)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    fname = _FUNDER_BY_ID[body.funder_id]["name"]
    desc = f"Funding option selected: {fname}"
    row = await db.fetchrow(
        """
        UPDATE projects
        SET selected_funder_id = $2,
            timeline_events = COALESCE(timeline_events, '[]'::jsonb) || $3::jsonb,
            updated_at = now()
        WHERE id = $1::uuid
        RETURNING *
        """,
        project_id,
        body.funder_id,
        _timeline_patch_json(desc),
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Update failed")
    return record_to_api_dict(row)


@router.get("/projects/{project_id}/inspection-slots")
async def list_inspection_slots(
    project_id: str,
    user: dict = Depends(get_current_homeowner),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    if await _can_access_project(db, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return {"slots": _inspection_slot_datetimes()}


@router.post("/projects/{project_id}/inspection-slots")
async def book_inspection_slot(
    project_id: str,
    body: BookInspectionBody,
    user: dict = Depends(get_current_homeowner),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    base = await _can_access_project(db, project_id, user)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    allowed = set(_inspection_slot_datetimes())
    chosen = body.slot_datetime.astimezone(timezone.utc).replace(second=0, microsecond=0)
    if chosen.isoformat() not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "datetime does not match an available slot",
        )

    cur_status = base.get("status") or "draft"
    new_status = cur_status
    advance_from = frozenset(
        {"draft", "designed", "drone_requested", "drone_completed"}
    )
    if cur_status in advance_from:
        new_status = "permit_submitted"

    when_dt = chosen
    desc = f"Inspection scheduled for {when_dt.isoformat()}"

    row = await db.fetchrow(
        """
        UPDATE projects
        SET inspection_scheduled_at = $2,
            status = $3,
            timeline_events = COALESCE(timeline_events, '[]'::jsonb) || $4::jsonb,
            updated_at = now()
        WHERE id = $1::uuid
        RETURNING *
        """,
        project_id,
        when_dt,
        new_status,
        _timeline_patch_json(desc),
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Update failed")
    return record_to_api_dict(row)


@router.get("/projects/{project_id}/timeline")
async def get_timeline(
    project_id: str,
    user: dict = Depends(get_current_homeowner),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    row = await _can_access_project(db, project_id, user)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    events = row.get("timeline_events") or []
    if not isinstance(events, list):
        events = []
    return {"events": events}


@router.get("/projects/{project_id}/documents")
async def get_documents(
    project_id: str,
    user: dict = Depends(get_current_homeowner),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    if await _can_access_project(db, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return {"documents": MOCK_DOCUMENTS}


@router.get("/projects/{project_id}/messages")
async def get_messages(
    project_id: str,
    user: dict = Depends(get_current_homeowner),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    row = await _can_access_project(db, project_id, user)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    msgs = row.get("dashboard_messages") or []
    if not isinstance(msgs, list):
        msgs = []
    return {"messages": msgs}


@router.post("/projects/{project_id}/messages")
async def post_message(
    project_id: str,
    body: MessageCreateBody,
    user: dict = Depends(get_current_homeowner),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    base = await _can_access_project(db, project_id, user)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    entry = {
        "id": str(uuid.uuid4()),
        "sentAt": _utc_now_iso(),
        "author": "homeowner",
        "body": body.body,
    }
    patch = json.dumps([entry])

    row = await db.fetchrow(
        """
        UPDATE projects
        SET dashboard_messages = COALESCE(dashboard_messages, '[]'::jsonb) || $2::jsonb,
            updated_at = now()
        WHERE id = $1::uuid
        RETURNING *
        """,
        project_id,
        patch,
    )
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Update failed")
    return entry
