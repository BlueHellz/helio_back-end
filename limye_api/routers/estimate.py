"""Auth-free detailed estimate (proposal) without persisting users or projects."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from limye_api.services.proposal_estimate import DesignParams, build_public_proposal

router = APIRouter(prefix="/estimate", tags=["estimate"])


@router.post("")
async def estimate(body: DesignParams) -> dict[str, Any]:
    return build_public_proposal(body)
