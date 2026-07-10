"""Tests for post-call agent pipeline."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import yaml
from langchain_core.messages import AIMessage, HumanMessage

from agents.orchestrator import build_transcript, run_post_call_pipeline
from agents.tools.context import ToolContext, clear_tool_context, set_tool_context
from agents.tools.save_call_record import save_call_record
from agents.tools.send_call_summary import send_call_summary
from db import get_call_record, init_db, seed_tenant, upsert_lead
from scripts.seed import DAVE_HVAC


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_DB_BACKEND", "sqlite")
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("MIRA_DB_PATH", str(db_path))
    init_db()
    seed_tenant(DAVE_HVAC)
    yield


def test_build_transcript():
    messages = [
        HumanMessage(content="My basement is flooding!"),
        AIMessage(content="Can I get your address?"),
        HumanMessage(content="42 Oak Street"),
    ]
    transcript = build_transcript(messages)
    assert "Caller: My basement is flooding!" in transcript
    assert "Mira: Can I get your address?" in transcript
    assert "Caller: 42 Oak Street" in transcript


def test_save_call_record_tool():
    session_id = str(uuid.uuid4())
    upsert_lead(
        session_id,
        "daves-hvac",
        {"caller_name": "Mike", "phone": "555-1234", "urgency": "emergency"},
    )
    ctx = ToolContext(
        session_id=session_id,
        tenant_id="daves-hvac",
        transcript="Caller: flooding\nMira: help is coming",
    )
    set_tool_context(ctx)
    try:
        result = json.loads(save_call_record.invoke({"summary": "Emergency flooding call from Mike."}))
    finally:
        clear_tool_context()

    assert result["saved"] is True
    record = get_call_record(session_id)
    assert record is not None
    assert record["summary"] == "Emergency flooding call from Mike."
    assert "flooding" in record["transcript"]


def test_send_call_summary_tool(capsys):
    session_id = str(uuid.uuid4())
    ctx = ToolContext(session_id=session_id, tenant_id="daves-hvac")
    set_tool_context(ctx)
    try:
        result = json.loads(
            send_call_summary.invoke({"summary": "Mike called about flooding."})
        )
    finally:
        clear_tool_context()

    assert result["summary_sent"] is True
    captured = capsys.readouterr()
    assert "CALL SUMMARY" in captured.out


def test_post_call_pipeline_skips_empty_transcript():
    result = run_post_call_pipeline(
        tenant_id="daves-hvac",
        session_id=str(uuid.uuid4()),
        messages=[],
    )
    assert result.get("skipped") is True


def test_post_call_scenarios_yaml_loads():
    path = Path(__file__).resolve().parents[1] / "evals" / "post_call_scenarios.yaml"
    scenarios = yaml.safe_load(path.read_text())
    assert len(scenarios) >= 3
    assert scenarios[0]["id"] == "emergency_call_summary"
