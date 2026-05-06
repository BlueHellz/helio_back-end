"""Save design to homeowner inbox: PDFs + SMTP (auth-free)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, ValidationError

from limye_api.services.market_estimate import ResolvedSolarDesign
from limye_api.services.proposal_email import ProposalEmailError, send_proposal_email_sync, smtp_configured
from limye_api.services.proposal_pdfs import render_design_pdf_bytes, render_estimate_pdf_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/save-design", tags=["design"])


class SaveDesignBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    designData: dict[str, Any]
    homeownerEmail: EmailStr
    estimateData: dict[str, Any] | None = None


@router.post("")
async def save_design(request: Request, body: SaveDesignBody) -> dict[str, Any]:
    """Generate design + proposal PDFs and email both to homeownerEmail."""
    settings = request.app.state.settings

    if not smtp_configured(settings):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Email delivery is not configured. Set SMTP_HOST and SMTP_FROM_EMAIL on the server.",
        )

    try:
        ResolvedSolarDesign.model_validate(body.designData)
    except ValidationError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors(include_url=False),
        ) from e

    has_estimate = body.estimateData is not None

    try:
        design_pdf = await asyncio.to_thread(render_design_pdf_bytes, body.designData)
        estimate_pdf = await asyncio.to_thread(
            render_estimate_pdf_bytes,
            body.designData,
            body.estimateData,
        )
        await asyncio.to_thread(
            send_proposal_email_sync,
            settings,
            str(body.homeownerEmail),
            design_pdf,
            estimate_pdf,
            has_full_estimate=has_estimate,
        )
    except ProposalEmailError as e:
        logger.warning("save-design email failed for %s: %s", body.homeownerEmail, e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    msg = (
        "Your solar design documents were sent successfully. Check your inbox (and spam) for "
        "the two PDF attachments."
        if has_estimate
        else "Your solar documents were sent successfully. The proposal PDF includes design "
        "highlights — run an estimate in the app before saving again to attach full pricing "
        "and savings detail."
    )
    return {"ok": True, "message": msg}


__all__ = ["router"]
