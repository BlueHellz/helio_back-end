"""One-page stub PDF reports."""

from __future__ import annotations

import asyncio
import io

from fastapi import APIRouter, Depends, HTTPException, Response, status
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from supabase import Client

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_user
from helios_api.routers.projects import _can_access_project

router = APIRouter(prefix="/reports", tags=["reports"])


def _pdf_bytes(project_id: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, h - 72, "Black Light — Solar Design Report (stub)")
    c.setFont("Helvetica", 11)
    c.drawString(72, h - 100, f"Project id: {project_id}")
    c.drawString(
        72,
        h - 120,
        "This placeholder PDF proves ReportLab + thread execution is wired.",
    )
    c.showPage()
    c.save()
    return buf.getvalue()


@router.get("/{project_id}/pdf")
async def download_report_pdf(
    project_id: str,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> Response:
    if _can_access_project(supabase, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    pdf = await asyncio.to_thread(_pdf_bytes, project_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="report-{project_id}.pdf"'},
    )
