"""Black Light conversational brain (SSE + DeepSeek).

Chat streaming remains a lightweight stub until full tool orchestration lands.
DeepSeek is called via OpenAI-compatible client for LIMYÈ configuration flows.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from openai import APIError as OpenAIAPIError
from openai import AsyncOpenAI

from helios_api.config import get_settings

logger = logging.getLogger(__name__)

BLACKLIGHT_SYSTEM_PROMPT = """You are Black Light AI — a solar-design expert who
guides homeowners and installers with precision, NEC-aware electrical reasoning,
honest ROI, and ethically sharp ninja sales psychology: build trust first,
surface urgency from data (not hype), and always tie savings to their roof and
usage. Refuse off-topic requests. When tools exist, call them instead of guessing."""

LIMYE_DEEPSEEK_MODEL_DEFAULT = "deepseek-chat"


async def deepseek_chat_completion(system_prompt: str, user_prompt: str) -> str:
    """One-shot DeepSeek Chat completion (OpenAI-compatible API). Raises on HTTP/API errors."""

    settings = get_settings()
    key = (settings.DEEPSEEK_API_KEY or "").strip()
    if not key:
        raise ValueError("DEEPSEEK_API_KEY is not configured")

    client = AsyncOpenAI(api_key=key, base_url=(settings.DEEPSEEK_BASE_URL or "").strip() or "https://api.deepseek.com/v1")
    try:
        completion = await client.chat.completions.create(
            model=LIMYE_DEEPSEEK_MODEL_DEFAULT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        choice = completion.choices[0].message.content
        return (choice or "").strip()
    except OpenAIAPIError:
        logger.exception("DeepSeek API error during chat completion")
        raise
    finally:
        await client.close()


async def run_blacklight_chat(project_id: str, message: str) -> AsyncIterator[str]:
    """Async token generator for SSE (mock streaming until tools + DeepSeek wire up).

    Yields short string chunks to simulate model streaming.
    """
    _ = project_id, message, BLACKLIGHT_SYSTEM_PROMPT  # wired in full implementation
    stub = (
        "Black Light stub: your message is received. "
        "DeepSeek + tool orchestration will stream here next."
    )
    for word in stub.split():
        yield word + " "
        await asyncio.sleep(0.02)
