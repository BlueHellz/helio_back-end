"""ReportLab: design reports, contracts, permit packs.

**CPU-bound** work must not block the event loop. Call blocking ReportLab APIs
from ``asyncio.to_thread`` (or a thread pool) from async route handlers.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any, Dict

# Placeholder: real templates will use ``reportlab.platypus`` and assets under
# ``helios_api/data/`` (logos) as needed.


def _render_report_sync(_payload: Dict[str, Any]) -> bytes:
    """Blocking body — implement with ReportLab; keep I/O in threads."""
    raise NotImplementedError("Implement ReportLab flow for design reports / contracts.")


async def render_design_report_pdf(payload: Dict[str, Any]) -> bytes:
    """Async facade: run ReportLab in a thread pool."""
    return await asyncio.to_thread(_render_report_sync, payload)
