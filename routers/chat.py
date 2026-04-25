from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.ai_brain import run_helios_chat

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    project_id: str | None = None

@router.post("/")
async def chat_endpoint(req: ChatRequest):
    try:
        reply = await run_helios_chat(req.message, req.project_id)
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
