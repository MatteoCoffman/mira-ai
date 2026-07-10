"""Mock SMS notification to business owner."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from agents.tools.context import get_tool_context
from db import get_tenant, log_notification, log_tool_call
from services.sms import resolve_owner_phone, send_owner_sms


@tool
def notify_owner(message: str) -> str:
    """Send an SMS summary to the business owner. Use for emergencies or when call ends."""
    ctx = get_tool_context()
    log_tool_call(ctx.session_id, "notify_owner", {"message": message})

    tenant = get_tenant(ctx.tenant_id)
    if not tenant:
        return json.dumps({"error": "Tenant not found", "sent": False})

    owner_phone = resolve_owner_phone(tenant.get("owner_sms_phone"))
    full_message = f"Mira — {tenant['business_name']}\n\n{message}"
    channel = send_owner_sms(owner_phone, full_message)
    notification_id = log_notification(
        ctx.tenant_id, ctx.session_id, full_message, channel=channel
    )

    return json.dumps(
        {
            "sent": True,
            "notification_id": notification_id,
            "owner_phone": owner_phone,
            "message": full_message,
            "channel": channel,
        }
    )
