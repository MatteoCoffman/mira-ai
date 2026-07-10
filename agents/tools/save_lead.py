"""Persist caller lead information."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from db import upsert_lead, log_tool_call
from agents.tools.context import get_tool_context


@tool
def save_lead(
    caller_name: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    urgency: str | None = None,
    reason: str | None = None,
    intent: str | None = None,
) -> str:
    """Save or update caller lead info for the current call session.

    urgency should be one of: emergency, soon, flexible, or unknown.
    intent examples: faq, book, message, emergency, unknown.
    """
    ctx = get_tool_context()
    fields = {
        k: v
        for k, v in {
            "caller_name": caller_name,
            "phone": phone,
            "address": address,
            "urgency": urgency,
            "reason": reason,
            "intent": intent,
        }.items()
        if v is not None
    }
    log_tool_call(ctx.session_id, "save_lead", fields)
    lead = upsert_lead(ctx.session_id, ctx.tenant_id, fields)
    return json.dumps(lead)
