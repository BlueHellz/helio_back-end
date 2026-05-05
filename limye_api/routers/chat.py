"""SSE chat stub."""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import asyncpg

from limye_api.db.database import get_db
from limye_api.routers.projects import fetch_project_by_id
from limye_api.services.ai_brain import run_limye_chat

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatBody(BaseModel):
    message: str = Field(min_length=1)


@router.post("")
async def chat_sse_guest(body: ChatBody) -> StreamingResponse:
    """Auth-free conversational stream without a persisted project."""

    async def events() -> AsyncIterator[bytes]:
        async for token in run_limye_chat("guest", body.message):
            payload = json.dumps({"token": token})
            yield f"data: {payload}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{project_id}")
async def chat_sse(
    project_id: str,
    body: ChatBody,
    db: asyncpg.Connection = Depends(get_db),
) -> StreamingResponse:
    if await fetch_project_by_id(db, project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    async def events() -> AsyncIterator[bytes]:
        async for token in run_limye_chat(project_id, body.message):
            payload = json.dumps({"token": token})
            yield f"data: {payload}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
