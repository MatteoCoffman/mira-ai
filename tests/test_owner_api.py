"""Tests for the read-only owner console API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from db import book_slot, init_db, list_open_slots, save_call_record
from scripts.seed import DAVE_HVAC, main as seed_main

OWNER_KEY = "test-owner-key"


@pytest.fixture
def owner_client(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_DB_BACKEND", "sqlite")
    monkeypatch.setenv("MIRA_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MIRA_OWNER_API_KEY", OWNER_KEY)
    monkeypatch.setenv("MIRA_VALIDATE_TWILIO_SIGNATURE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MIRA_CORS_ORIGINS", "http://localhost:3000")

    mock_graph = MagicMock()
    with patch("api.main.build_receptionist_graph", return_value=mock_graph):
        from api.main import app

        init_db()
        seed_main()
        with TestClient(app) as client:
            yield client


def test_owner_rejects_missing_key(owner_client):
    response = owner_client.get("/owner/tenants")
    assert response.status_code == 401


def test_owner_lists_tenants(owner_client):
    response = owner_client.get(
        "/owner/tenants",
        headers={"X-Mira-Owner-Key": OWNER_KEY},
    )
    assert response.status_code == 200
    ids = {t["tenant_id"] for t in response.json()["tenants"]}
    assert "daves-hvac" in ids
    assert "pest-pros" in ids
    assert "mikes-plumbing" in ids


def test_owner_lists_calls_and_appointments(owner_client):
    save_call_record(
        call_id="CA-owner-1",
        tenant_id=DAVE_HVAC["tenant_id"],
        transcript="Caller: AC is warm\nMira: I can help book a visit.",
        summary="Caller needs AC service.",
        lead={"caller_name": "Alex", "phone": "+15551112222"},
        urgency="normal",
        intent="book",
    )
    slots = list_open_slots(DAVE_HVAC["tenant_id"], limit=1)
    assert slots
    book_slot(
        DAVE_HVAC["tenant_id"],
        slots[0]["slot_id"],
        session_id="CA-owner-1",
        caller_name="Alex",
        phone="+15551112222",
    )

    headers = {"X-Mira-Owner-Key": OWNER_KEY}
    calls = owner_client.get(
        f"/owner/tenants/{DAVE_HVAC['tenant_id']}/calls",
        headers=headers,
    )
    assert calls.status_code == 200
    assert any(c["call_id"] == "CA-owner-1" for c in calls.json()["calls"])

    appts = owner_client.get(
        f"/owner/tenants/{DAVE_HVAC['tenant_id']}/appointments",
        headers=headers,
    )
    assert appts.status_code == 200
    assert len(appts.json()["appointments"]) >= 1


def test_cors_preflight_allows_configured_origin(owner_client):
    response = owner_client.options(
        "/owner/tenants",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Mira-Owner-Key",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
