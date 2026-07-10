"""Orchestrates receptionist and post-call agent pipelines."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from agents.post_call import build_post_call_graph, invoke_post_call
from agents.receptionist import build_receptionist_graph, invoke_turn
from db import get_lead, get_session_created_at


def build_transcript(messages: list) -> str:
    lines: list[str] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"Caller: {msg.content}")
        elif isinstance(msg, AIMessage) and msg.content and str(msg.content).strip():
            lines.append(f"Mira: {msg.content}")
    return "\n".join(lines)


def run_receptionist_turn(
    graph,
    *,
    tenant_id: str,
    session_id: str,
    user_text: str,
    prior_state: dict | None = None,
    prior_messages: list | None = None,
):
    return invoke_turn(
        graph,
        tenant_id=tenant_id,
        session_id=session_id,
        user_text=user_text,
        prior_state=prior_state,
        prior_messages=prior_messages,
    )


def run_post_call_pipeline(
    *,
    tenant_id: str,
    session_id: str,
    messages: list,
    dialog_state: dict | None = None,
    started_at: str | None = None,
) -> dict:
    transcript = build_transcript(messages)
    if not transcript.strip():
        return {"skipped": True, "reason": "empty transcript"}

    lead_row = get_lead(session_id) or {}
    lead = dialog_state.get("collected", {}) if dialog_state else {}
    if not lead:
        lead = {
            k: lead_row.get(k)
            for k in ("caller_name", "phone", "address", "urgency", "reason", "intent")
            if lead_row.get(k)
        }

    graph = build_post_call_graph()
    return invoke_post_call(
        graph,
        tenant_id=tenant_id,
        session_id=session_id,
        transcript=transcript,
        lead=lead,
        started_at=started_at,
    )


def get_session_started_at(session_id: str) -> str | None:
    return get_session_created_at(session_id)
