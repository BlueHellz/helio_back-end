"""SSE chat stub."""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

from helios_api.db.supabase import get_supabase
from helios_api.middleware.auth import get_current_user
from helios_api.routers.projects import _can_access_project
from helios_api.services.ai_brain import run_blacklight_chat

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatBody(BaseModel):
    message: str = Field(min_length=1)


@router.post("/{project_id}")
async def chat_sse(
    project_id: str,
    body: ChatBody,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> StreamingResponse:
    if _can_access_project(supabase, project_id, user) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    async def events() -> AsyncIterator[bytes]:
        async for token in run_blacklight_chat(project_id, body.message):
            payload = json.dumps({"token": token})
            yield f"data: {payload}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
