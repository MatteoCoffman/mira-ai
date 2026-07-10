"""Tool context injected at runtime (session_id, tenant_id)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

_context: ContextVar["ToolContext | None"] = ContextVar("tool_context", default=None)


@dataclass
class ToolContext:
    session_id: str
    tenant_id: str
    transcript: str | None = None
    started_at: str | None = None


def set_tool_context(ctx: ToolContext) -> None:
    _context.set(ctx)


def get_tool_context() -> ToolContext:
    ctx = _context.get()
    if ctx is None:
        raise RuntimeError("Tool context not set. Wrap agent invoke in set_tool_context.")
    return ctx


def clear_tool_context() -> None:
    _context.set(None)
