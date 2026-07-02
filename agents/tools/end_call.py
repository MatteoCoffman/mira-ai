"""End the current call."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from agents.tools.context import get_tool_context
from db.sqlite import log_tool_call


@tool
def end_call(summary: str | None = None) -> str:
    """End the call when all necessary information has been collected or FAQ answered."""
    ctx = get_tool_context()
    log_tool_call(ctx.session_id, "end_call", {"summary": summary})
    return json.dumps({"should_end_call": True, "summary": summary})
