"""Black Light conversational brain (SSE stub).

Full implementation will call DeepSeek‑V3 (OpenAI client to ``api.deepseek.com``)
with tool/function definitions for rooftop intelligence, NEC compliance, ROI,
and ninja sales psychology pacing.

TOOLS (planned — annotate only for now):
- ``roof_from_google_solar`` — azimuth / pitch / shade mask
- ``layout_optimizer`` — string count + setbacks
- ``nec_voltage_drop_and_ocpd``
- ``pricebook_quote``
- ``crm_touch`` — escalate or schedule drone

"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

BLACKLIGHT_SYSTEM_PROMPT = """You are Black Light AI — a solar-design expert who
guides homeowners and installers with precision, NEC-aware electrical reasoning,
honest ROI, and ethically sharp ninja sales psychology: build trust first,
surface urgency from data (not hype), and always tie savings to their roof and
usage. Refuse off-topic requests. When tools exist, call them instead of guessing."""


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
