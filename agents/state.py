"""LangGraph state for Mira agents."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class CollectedFields(TypedDict, total=False):
    caller_name: str
    phone: str
    address: str
    urgency: str
    reason: str
    intent: str


class MiraState(TypedDict):
    messages: Annotated[list, add_messages]
    tenant_id: str
    session_id: str
    collected: CollectedFields
    urgency: str
    intent: str
    escalate: bool
    should_end_call: bool
    owner_notified: bool
    pending_owner_notify: bool
    tool_calls_log: list[str]


class PostCallState(TypedDict):
    messages: Annotated[list, add_messages]
    session_id: str
    tenant_id: str
    transcript: str
    summary: str
    record_saved: bool
    summary_sent: bool
