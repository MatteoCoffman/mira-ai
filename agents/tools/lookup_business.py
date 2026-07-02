"""Look up tenant business info and FAQ."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from db.sqlite import get_tenant, log_tool_call
from agents.tools.context import get_tool_context


@tool
def lookup_business(tenant_id: str | None = None) -> str:
    """Look up business hours, services, service area, and FAQ for the current tenant."""
    ctx = get_tool_context()
    tid = tenant_id or ctx.tenant_id
    log_tool_call(ctx.session_id, "lookup_business", {"tenant_id": tid})

    tenant = get_tenant(tid)
    if not tenant:
        return json.dumps({"error": f"Tenant not found: {tid}"})

    return json.dumps(
        {
            "business_name": tenant["business_name"],
            "hours": tenant["hours"],
            "services": tenant["services"],
            "service_area": tenant["service_area"],
            "faq": tenant["faq"],
            "emergency_keywords": tenant["emergency_keywords"],
        }
    )
