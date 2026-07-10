"""Tests for Mira tools and database."""

from __future__ import annotations

import json
import os
import uuid

import pytest

from db import count_notifications, get_tenant, init_db, seed_tenant
from agents.tools.context import ToolContext, clear_tool_context, set_tool_context
from agents.tools.lookup_business import lookup_business
from agents.tools.notify_owner import notify_owner
from agents.tools.save_lead import save_lead
from scripts.seed import DAVE_HVAC


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_DB_BACKEND", "sqlite")
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("MIRA_DB_PATH", str(db_path))
    init_db()
    seed_tenant(DAVE_HVAC)
    yield


def test_lookup_business_returns_faq():
    ctx = ToolContext(session_id="sess-1", tenant_id="daves-hvac")
    set_tool_context(ctx)
    try:
        result = json.loads(lookup_business.invoke({"tenant_id": "daves-hvac"}))
    finally:
        clear_tool_context()

    assert result["business_name"] == "Dave's HVAC"
    assert any("hours" in item.get("q", "").lower() for item in result["faq"])


def test_save_lead_persists():
    session_id = str(uuid.uuid4())
    ctx = ToolContext(session_id=session_id, tenant_id="daves-hvac")
    set_tool_context(ctx)
    try:
        save_lead.invoke(
            {
                "caller_name": "Mike",
                "phone": "555-1234",
                "urgency": "emergency",
                "reason": "flooding",
            }
        )
    finally:
        clear_tool_context()

    from db import get_lead

    lead = get_lead(session_id)
    assert lead is not None
    assert lead["caller_name"] == "Mike"
    assert lead["urgency"] == "emergency"


def test_notify_owner_logs_notification(capsys):
    session_id = str(uuid.uuid4())
    ctx = ToolContext(session_id=session_id, tenant_id="daves-hvac")
    set_tool_context(ctx)
    try:
        result = json.loads(
            notify_owner.invoke({"message": "Test emergency notification"})
        )
    finally:
        clear_tool_context()

    assert result["sent"] is True
    assert count_notifications(session_id) == 1
    captured = capsys.readouterr()
    assert "MOCK SMS" in captured.out


def test_get_tenant():
    tenant = get_tenant("daves-hvac")
    assert tenant is not None
    assert tenant["business_name"] == "Dave's HVAC"
    assert "flooding" in tenant["emergency_keywords"]
