"""Book an open appointment slot for the current call session."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from agents.tools.context import get_tool_context
from db import book_slot, get_lead, log_tool_call, upsert_lead


@tool
def book_appointment(
    slot_id: str,
    caller_name: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    reason: str | None = None,
) -> str:
    """Book an open slot for this caller. Use slot_id from check_availability.

    Pass caller_name, phone, and address when available. Fails if the slot is
    already booked. Prefer save_lead first so contact info is persisted.
    """
    ctx = get_tool_context()
    fields = {
        k: v
        for k, v in {
            "caller_name": caller_name,
            "phone": phone,
            "address": address,
            "reason": reason,
            "intent": "book",
        }.items()
        if v is not None
    }
    log_tool_call(
        ctx.session_id,
        "book_appointment",
        {"slot_id": slot_id, **fields},
    )

    if fields:
        upsert_lead(ctx.session_id, ctx.tenant_id, fields)

    lead = get_lead(ctx.session_id) or {}
    try:
        appointment = book_slot(
            ctx.tenant_id,
            slot_id,
            session_id=ctx.session_id,
            caller_name=caller_name or lead.get("caller_name"),
            phone=phone or lead.get("phone"),
            address=address or lead.get("address"),
            reason=reason or lead.get("reason"),
        )
    except ValueError as exc:
        return json.dumps({"booked": False, "error": str(exc)})

    return json.dumps(
        {
            "booked": True,
            "appointment_id": appointment.get("appointment_id"),
            "slot_id": appointment.get("slot_id"),
            "label": appointment.get("label"),
            "starts_at": appointment.get("starts_at"),
            "caller_name": appointment.get("caller_name"),
        }
    )
