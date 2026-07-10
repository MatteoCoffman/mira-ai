"""Tests for receptionist helpers and eval loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.receptionist import (
    _detect_emergency,
    _missing_required_fields,
    get_last_ai_reply,
    messages_from_serializable,
    messages_to_serializable,
)


def test_detect_emergency_keywords():
    assert _detect_emergency("My basement is flooding!", ["flooding"])
    assert _detect_emergency("HELP gas leak", [])
    assert not _detect_emergency("What are your hours?", ["flooding"])


def test_missing_required_fields_faq_vs_service():
    assert "address" in _missing_required_fields({"intent": "book"})
    assert "address" not in _missing_required_fields({"intent": "faq"})
    assert "caller_name" in _missing_required_fields({})


def test_get_last_ai_reply_uses_current_turn_not_stale_message():
    messages = [
        HumanMessage(content="My basement is flooding!"),
        AIMessage(content="Can I have your name, phone, and address?"),
        HumanMessage(content="Mike, 555-1234, 42 Oak Street"),
        AIMessage(content="", tool_calls=[{"name": "save_lead", "args": {}, "id": "1"}]),
        ToolMessage(content='{"caller_name": "Mike"}', tool_call_id="1", name="save_lead"),
        AIMessage(content="Thanks Mike — I've alerted Dave and help is on the way."),
    ]
    assert get_last_ai_reply(messages) == (
        "Thanks Mike — I've alerted Dave and help is on the way."
    )


def test_messages_from_serializable_ai_without_tool_calls():
    serialized = [
        {"role": "human", "content": "My basement is flooding!"},
        {"role": "ai", "content": "Can I have your name, phone, and address?"},
    ]
    messages = messages_from_serializable(serialized)
    assert len(messages) == 2
    assert isinstance(messages[1], AIMessage)
    assert messages[1].tool_calls == []


def test_messages_round_trip_preserves_tool_calls():
    original = [
        HumanMessage(content="help"),
        AIMessage(content="", tool_calls=[{"name": "save_lead", "args": {}, "id": "1"}]),
    ]
    restored = messages_from_serializable(messages_to_serializable(original))
    assert len(restored) == 2
    assert restored[1].tool_calls[0]["name"] == "save_lead"


def test_scenarios_yaml_loads():
    path = Path(__file__).resolve().parents[1] / "evals" / "scenarios.yaml"
    scenarios = yaml.safe_load(path.read_text())
    assert len(scenarios) == 10
    assert scenarios[0]["id"] == "emergency_flooding"
