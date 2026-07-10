"""List open appointment slots for the current tenant."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from agents.tools.context import get_tool_context
from db import list_open_slots, log_tool_call


@tool
def check_availability(day_preference: str | None = None) -> str:
    """List open appointment slots the caller can book.

    Optionally pass day_preference like "tomorrow", "Friday", or "morning"
    to filter spoken labels. Returns slot_id values to use with book_appointment.
    """
    ctx = get_tool_context()
    log_tool_call(
        ctx.session_id,
        "check_availability",
        {"day_preference": day_preference},
    )
    slots = list_open_slots(ctx.tenant_id, limit=8)
    if day_preference:
        pref = day_preference.strip().lower()
        filtered = [s for s in slots if pref in (s.get("label") or "").lower()]
        if filtered:
            slots = filtered

    payload = [
        {
            "slot_id": s["slot_id"],
            "label": s["label"],
            "starts_at": s["starts_at"],
        }
        for s in slots[:6]
    ]
    return json.dumps({"slots": payload, "count": len(payload)})
