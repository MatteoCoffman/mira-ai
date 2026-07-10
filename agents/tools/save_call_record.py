"""Persist completed call transcript and summary."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from agents.tools.context import get_tool_context
from db import get_lead, log_tool_call, save_call_record as db_save_call_record


@tool
def save_call_record(summary: str) -> str:
    """Save the completed call record with a concise summary for the business owner."""
    ctx = get_tool_context()
    if not ctx.transcript:
        return json.dumps({"error": "No transcript in context", "saved": False})

    log_tool_call(ctx.session_id, "save_call_record", {"summary": summary})
    lead_row = get_lead(ctx.session_id) or {}
    lead = {
        k: lead_row.get(k)
        for k in ("caller_name", "phone", "address", "urgency", "reason", "intent")
        if lead_row.get(k)
    }

    record = db_save_call_record(
        call_id=ctx.session_id,
        tenant_id=ctx.tenant_id,
        transcript=ctx.transcript,
        summary=summary,
        lead=lead,
        urgency=lead.get("urgency"),
        intent=lead.get("intent"),
        started_at=ctx.started_at,
    )
    return json.dumps({"saved": True, "call_id": record.get("call_id"), "summary": summary})
