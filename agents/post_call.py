"""LangGraph post-call summarizer agent."""

from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agents.prompts import build_post_call_prompt
from agents.state import PostCallState
from agents.tools import POST_CALL_TOOLS
from agents.tools.context import ToolContext, clear_tool_context, set_tool_context
from db import get_appointment_for_session, get_call_record, get_tenant, get_tool_calls


def build_post_call_graph():
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, max_tokens=500)
    model_with_tools = model.bind_tools(POST_CALL_TOOLS)
    tool_node = ToolNode(POST_CALL_TOOLS)

    def call_model(state: PostCallState) -> dict:
        tenant = get_tenant(state["tenant_id"])
        if not tenant:
            raise ValueError(f"Unknown tenant: {state['tenant_id']}")

        system = build_post_call_prompt(tenant)
        messages = [SystemMessage(content=system), *state["messages"]]
        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    def run_tools(state: PostCallState) -> dict:
        ctx = ToolContext(
            session_id=state["session_id"],
            tenant_id=state["tenant_id"],
            transcript=state["transcript"],
        )
        set_tool_context(ctx)
        try:
            return tool_node.invoke(state)
        finally:
            clear_tool_context()

    def sync_results(state: PostCallState) -> dict:
        tool_log = get_tool_calls(state["session_id"])
        record = get_call_record(state["session_id"])
        summary = record.get("summary", "") if record else state.get("summary", "")
        return {
            "record_saved": "save_call_record" in tool_log or record is not None,
            "summary_sent": "send_call_summary" in tool_log,
            "summary": summary,
        }

    def should_continue_after_agent(state: PostCallState) -> Literal["tools", "sync"]:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "sync"

    def should_continue_after_sync(state: PostCallState) -> Literal["agent", "end"]:
        if isinstance(state["messages"][-1], ToolMessage):
            return "agent"
        if state.get("record_saved") and state.get("summary_sent"):
            return "end"
        return "end"

    graph = StateGraph(PostCallState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", run_tools)
    graph.add_node("sync", sync_results)

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
        {"agent": "agent", "end": END},
    )

    return graph.compile()


def invoke_post_call(
    graph,
    *,
    tenant_id: str,
    session_id: str,
    transcript: str,
    lead: dict,
    started_at: str | None = None,
) -> dict:
    ctx = ToolContext(
        session_id=session_id,
        tenant_id=tenant_id,
        transcript=transcript,
        started_at=started_at,
    )
    set_tool_context(ctx)
    try:
        appointment = get_appointment_for_session(session_id) or {}
        initial = HumanMessage(
            content=(
                f"Process this completed call.\n\n"
                f"Transcript:\n{transcript}\n\n"
                f"Lead data:\n{json.dumps(lead, indent=2)}\n\n"
                f"Appointment data:\n{json.dumps(appointment, indent=2)}"
            )
        )
        result = graph.invoke(
            {
                "messages": [initial],
                "session_id": session_id,
                "tenant_id": tenant_id,
                "transcript": transcript,
                "summary": "",
                "record_saved": False,
                "summary_sent": False,
            }
        )
    finally:
        clear_tool_context()

    record = get_call_record(session_id)
    return {
        "call_id": session_id,
        "summary": result.get("summary") or (record.get("summary") if record else ""),
        "record_saved": result.get("record_saved", False),
        "summary_sent": result.get("summary_sent", False),
        "record": record,
        "appointment": get_appointment_for_session(session_id),
    }
