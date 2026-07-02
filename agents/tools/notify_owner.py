"""Mock SMS notification to business owner."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from db.sqlite import get_tenant, log_notification, log_tool_call
from agents.tools.context import get_tool_context


@tool
def notify_owner(message: str) -> str:
    """Send an SMS summary to the business owner. Use for emergencies or when call ends."""
    ctx = get_tool_context()
    log_tool_call(ctx.session_id, "notify_owner", {"message": message})

    tenant = get_tenant(ctx.tenant_id)
    if not tenant:
        return json.dumps({"error": "Tenant not found", "sent": False})

    owner_phone = tenant.get("owner_sms_phone") or "unknown"
    full_message = f"Mira — {tenant['business_name']}\n\n{message}"
    notification_id = log_notification(ctx.tenant_id, ctx.session_id, full_message)

    print(f"\n📱 [MOCK SMS → {owner_phone}]\n{full_message}\n")

    return json.dumps(
        {
            "sent": True,
            "notification_id": notification_id,
            "owner_phone": owner_phone,
            "message": full_message,
        }
    )
