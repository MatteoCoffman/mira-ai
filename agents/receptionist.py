"""LangGraph receptionist agent for Mira."""

from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agents.prompts import build_system_prompt
from agents.state import MiraState
from agents.tools import AGENT_TOOLS
from agents.tools.context import ToolContext, set_tool_context, clear_tool_context
from agents.tools.notify_owner import notify_owner
from db import get_lead, get_tenant, get_tool_calls, upsert_lead

EMERGENCY_KEYWORDS = {
    "flooding",
    "flood",
    "gas leak",
    "no heat",
    "water everywhere",
    "burst pipe",
    "electrical fire",
    "sewage",
}


def _detect_emergency(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    for kw in keywords:
        if kw.lower() in lower:
            return True
    for kw in EMERGENCY_KEYWORDS:
        if kw in lower:
            return True
    return False


def _missing_required_fields(collected: dict) -> list[str]:
    missing = []
    if not collected.get("caller_name"):
        missing.append("caller_name")
    if not collected.get("phone"):
        missing.append("phone")
    if collected.get("intent") not in ("faq",) and not collected.get("address"):
        missing.append("address")
    return missing


def build_receptionist_graph():
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    model_with_tools = model.bind_tools(AGENT_TOOLS)
    tool_node = ToolNode(AGENT_TOOLS)

    def call_model(state: MiraState) -> dict:
        tenant = get_tenant(state["tenant_id"])
        if not tenant:
            raise ValueError(f"Unknown tenant: {state['tenant_id']}")

        system = build_system_prompt(tenant)
        collected = state.get("collected") or {}
        missing = _missing_required_fields(collected)
        owner_notified = state.get("owner_notified", False)
        context_note = (
            f"\nCurrent collected fields: {json.dumps(collected)}. "
            f"Missing contact fields for booking/dispatch: {missing or 'none'}. "
            f"Inferred urgency: {state.get('urgency', 'unknown')}. "
            f"Escalate: {state.get('escalate', False)}. "
            f"Owner notified: {owner_notified}."
        )
        if state.get("urgency") == "emergency" and missing:
            context_note += " Emergency — ask only for the missing contact fields."
        elif owner_notified:
            context_note += (
                " All required info is collected and the owner has been alerted. "
                "Confirm help is on the way and do not re-ask for name, phone, or address."
            )
        elif "book_appointment" in (state.get("tool_calls_log") or []):
            context_note += " Appointment already booked — confirm the time and end the call."
        messages = [SystemMessage(content=system + context_note), *state["messages"]]
        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    def run_tools(state: MiraState) -> dict:
        ctx = ToolContext(session_id=state["session_id"], tenant_id=state["tenant_id"])
        set_tool_context(ctx)
        try:
            result = tool_node.invoke(state)
        finally:
            clear_tool_context()
        return result

    def sync_from_db(state: MiraState) -> dict:
        lead = get_lead(state["session_id"]) or {}
        collected = {
            k: lead.get(k)
            for k in ("caller_name", "phone", "address", "urgency", "reason", "intent")
            if lead.get(k)
        }
        urgency = lead.get("urgency") or state.get("urgency") or "unknown"
        intent = lead.get("intent") or state.get("intent") or "unknown"
        escalate = urgency == "emergency" or state.get("escalate", False)

        tenant = get_tenant(state["tenant_id"]) or {}
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage) and _detect_emergency(
                msg.content, tenant.get("emergency_keywords", [])
            ):
                urgency = "emergency"
                intent = "emergency"
                escalate = True

        if urgency == "emergency":
            upsert_lead(
                state["session_id"],
                state["tenant_id"],
                {"urgency": "emergency", "intent": intent or "emergency"},
            )
            lead = get_lead(state["session_id"]) or lead
            collected = {
                k: lead.get(k)
                for k in ("caller_name", "phone", "address", "urgency", "reason", "intent")
                if lead.get(k)
            }
            urgency = lead.get("urgency") or urgency

        owner_notified = state.get("owner_notified", False)
        if "notify_owner" in get_tool_calls(state["session_id"]):
            owner_notified = True

        pending = (
            urgency == "emergency"
            and bool(collected.get("address"))
            and not owner_notified
        )

        tool_log = get_tool_calls(state["session_id"])

        updates: dict = {
            "collected": collected,
            "urgency": urgency,
            "intent": intent,
            "escalate": escalate,
            "owner_notified": owner_notified,
            "pending_owner_notify": pending,
            "tool_calls_log": tool_log,
        }

        if "end_call" in tool_log:
            updates["should_end_call"] = True

        return updates

    def force_notify_owner(state: MiraState) -> dict:
        if state.get("owner_notified") or not state.get("pending_owner_notify"):
            return {}

        collected = state.get("collected") or {}
        message = (
            f"EMERGENCY CALL\n"
            f"Name: {collected.get('caller_name', 'unknown')}\n"
            f"Phone: {collected.get('phone', 'unknown')}\n"
            f"Address: {collected.get('address', 'unknown')}\n"
            f"Reason: {collected.get('reason', 'unknown')}"
        )

        ctx = ToolContext(session_id=state["session_id"], tenant_id=state["tenant_id"])
        set_tool_context(ctx)
        try:
            notify_owner.invoke({"message": message})
        finally:
            clear_tool_context()

        return {"owner_notified": True, "pending_owner_notify": False}

    def should_continue_after_agent(state: MiraState) -> Literal["tools", "sync"]:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "sync"

    def should_continue_after_sync(state: MiraState) -> Literal["notify", "agent", "end"]:
        if state.get("pending_owner_notify") and not state.get("owner_notified"):
            return "notify"
        if isinstance(state["messages"][-1], ToolMessage):
            return "agent"
        return "end"

    graph = StateGraph(MiraState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", run_tools)
    graph.add_node("sync", sync_from_db)
    graph.add_node("notify", force_notify_owner)

    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        should_continue_after_agent,
        {"tools": "tools", "sync": "sync"},
    )
    graph.add_edge("tools", "sync")
    graph.add_conditional_edges(
        "sync",
        should_continue_after_sync,
        {"notify": "notify", "agent": "agent", "end": END},
    )
    graph.add_edge("notify", "agent")

    return graph.compile()


def messages_to_serializable(messages: list) -> list[dict]:
    out = []
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "human", "content": m.content})
        elif isinstance(m, AIMessage):
            entry: dict = {"role": "ai", "content": m.content or ""}
            if m.tool_calls:
                entry["tool_calls"] = m.tool_calls
            out.append(entry)
        elif isinstance(m, ToolMessage):
            out.append(
                {
                    "role": "tool",
                    "content": m.content,
                    "tool_call_id": m.tool_call_id,
                    "name": m.name,
                }
            )
        elif isinstance(m, SystemMessage):
            out.append({"role": "system", "content": m.content})
    return out


def messages_from_serializable(data: list[dict]) -> list:
    messages = []
    for item in data:
        role = item["role"]
        if role == "human":
            messages.append(HumanMessage(content=item["content"]))
        elif role == "ai":
            kwargs: dict = {"content": item.get("content", "")}
            tool_calls = item.get("tool_calls")
            if tool_calls:
                kwargs["tool_calls"] = tool_calls
            messages.append(AIMessage(**kwargs))
        elif role == "tool":
            messages.append(
                ToolMessage(
                    content=item["content"],
                    tool_call_id=item["tool_call_id"],
                    name=item.get("name", ""),
                )
            )
        elif role == "system":
            messages.append(SystemMessage(content=item["content"]))
    return messages


def get_last_ai_reply(messages: list) -> str:
    """Return the latest spoken AI reply for the current turn (since last caller message)."""
    last_human_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    turn_messages = messages[last_human_idx + 1 :] if last_human_idx >= 0 else messages
    for msg in reversed(turn_messages):
        if isinstance(msg, AIMessage) and msg.content and str(msg.content).strip():
            return str(msg.content)
    return "I'm sorry, could you repeat that?"


def invoke_turn(
    graph,
    *,
    tenant_id: str,
    session_id: str,
    user_text: str,
    prior_state: dict | None = None,
    prior_messages: list | None = None,
) -> tuple[dict, list, str]:
    base_state: MiraState = {
        "messages": list(prior_messages or []) + [HumanMessage(content=user_text)],
        "tenant_id": tenant_id,
        "session_id": session_id,
        "collected": (prior_state or {}).get("collected", {}),
        "urgency": (prior_state or {}).get("urgency", "unknown"),
        "intent": (prior_state or {}).get("intent", "unknown"),
        "escalate": (prior_state or {}).get("escalate", False),
        "should_end_call": (prior_state or {}).get("should_end_call", False),
        "owner_notified": (prior_state or {}).get("owner_notified", False),
        "pending_owner_notify": (prior_state or {}).get("pending_owner_notify", False),
        "tool_calls_log": [],
    }

    result = graph.invoke(base_state)
    reply = get_last_ai_reply(result["messages"])
    state_out = {
        "collected": result.get("collected", {}),
        "urgency": result.get("urgency", "unknown"),
        "intent": result.get("intent", "unknown"),
        "escalate": result.get("escalate", False),
        "should_end_call": result.get("should_end_call", False),
        "owner_notified": result.get("owner_notified", False),
        "pending_owner_notify": result.get("pending_owner_notify", False),
    }
    return state_out, result["messages"], reply
