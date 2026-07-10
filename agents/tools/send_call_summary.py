"""Send post-call summary SMS to business owner."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from agents.tools.context import get_tool_context, set_tool_context
from agents.tools.notify_owner import notify_owner
from db import log_tool_call


@tool
def send_call_summary(summary: str) -> str:
    """Send the full call summary to the business owner after the call ends."""
    ctx = get_tool_context()
    log_tool_call(ctx.session_id, "send_call_summary", {"summary": summary})

    message = f"CALL SUMMARY\n\n{summary}"
    set_tool_context(ctx)
    result = json.loads(notify_owner.invoke({"message": message}))
    result["summary_sent"] = result.get("sent", False)
    return json.dumps(result)
