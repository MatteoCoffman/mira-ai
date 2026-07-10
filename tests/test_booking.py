"""Tests for computed availability and appointment booking."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from agents.tools.book_appointment import book_appointment
from agents.tools.check_availability import check_availability
from agents.tools.context import ToolContext, clear_tool_context, set_tool_context
from db import (
    book_slot,
    get_appointment_for_session,
    init_db,
    list_booked_slot_ids,
    list_open_slots,
    seed_tenant,
)
from scripts.seed import DAVE_HVAC, MIKES_PLUMBING, PEST_PROS
from services.scheduling import (
    DEFAULT_DAYS_AHEAD,
    DEMO_TZ,
    build_candidate_slots,
    get_candidate_slot,
)


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_DB_BACKEND", "sqlite")
    monkeypatch.setenv("MIRA_DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_tenant(DAVE_HVAC)
    seed_tenant(PEST_PROS)
    seed_tenant(MIKES_PLUMBING)
    yield


def test_build_candidate_slots_covers_two_weeks():
    now = datetime(2026, 7, 10, 12, 0, tzinfo=DEMO_TZ)
    slots = build_candidate_slots(days_ahead=DEFAULT_DAYS_AHEAD, now=now)
    assert len(slots) >= 8
    assert all("label" in s and "slot_id" in s for s in slots)
    last = datetime.fromisoformat(slots[-1]["starts_at"])
    assert (last.astimezone(DEMO_TZ).date() - now.date()).days <= DEFAULT_DAYS_AHEAD


def test_tenants_have_distinct_schedules():
    now = datetime(2026, 7, 10, 7, 0, tzinfo=DEMO_TZ)  # Friday morning
    dave = build_candidate_slots(scheduling=DAVE_HVAC["scheduling"], now=now)
    pest = build_candidate_slots(scheduling=PEST_PROS["scheduling"], now=now)
    mike = build_candidate_slots(scheduling=MIKES_PLUMBING["scheduling"], now=now)

    dave_hours = {datetime.fromisoformat(s["starts_at"]).astimezone(DEMO_TZ).hour for s in dave}
    pest_hours = {datetime.fromisoformat(s["starts_at"]).astimezone(DEMO_TZ).hour for s in pest}
    mike_hours = {datetime.fromisoformat(s["starts_at"]).astimezone(DEMO_TZ).hour for s in mike}
    assert dave_hours == {9, 13}
    assert pest_hours == {10, 14}
    assert mike_hours == {8, 11, 15}

    # Pest Pros books Saturdays; Dave does not
    pest_days = {
        datetime.fromisoformat(s["starts_at"]).astimezone(DEMO_TZ).weekday() for s in pest
    }
    dave_days = {
        datetime.fromisoformat(s["starts_at"]).astimezone(DEMO_TZ).weekday() for s in dave
    }
    assert 5 in pest_days
    assert 5 not in dave_days


def test_list_open_slots_uses_tenant_schedule():
    dave = list_open_slots("daves-hvac", limit=6)
    pest = list_open_slots("pest-pros", limit=6)
    assert dave and pest
    dave_hour = datetime.fromisoformat(dave[0]["starts_at"]).astimezone(DEMO_TZ).hour
    pest_hour = datetime.fromisoformat(pest[0]["starts_at"]).astimezone(DEMO_TZ).hour
    assert dave_hour in (9, 13)
    assert pest_hour in (10, 14)
    assert dave[0]["slot_id"] != pest[0]["slot_id"] or dave_hour != pest_hour


def test_book_slot_creates_appointment_and_removes_from_open():
    slots = list_open_slots("daves-hvac", limit=1)
    slot_id = slots[0]["slot_id"]
    session_id = str(uuid.uuid4())

    appointment = book_slot(
        "daves-hvac",
        slot_id,
        session_id=session_id,
        caller_name="Matteo",
        phone="5125551212",
        address="4005 Amy Circle",
        reason="AC repair",
    )
    assert appointment["status"] == "booked"
    assert appointment["slot_id"] == slot_id
    assert slot_id in list_booked_slot_ids("daves-hvac")
    assert slot_id not in {s["slot_id"] for s in list_open_slots("daves-hvac", limit=20)}
    assert get_appointment_for_session(session_id)["appointment_id"] == appointment[
        "appointment_id"
    ]


def test_double_book_fails():
    slots = list_open_slots("daves-hvac", limit=1)
    slot_id = slots[0]["slot_id"]
    book_slot("daves-hvac", slot_id, session_id="s1", caller_name="A")
    with pytest.raises(ValueError, match="not available"):
        book_slot("daves-hvac", slot_id, session_id="s2", caller_name="B")


def test_unknown_slot_rejected():
    with pytest.raises(ValueError, match="not found"):
        book_slot("daves-hvac", "1999-01-01T00:00", session_id="s1")


def test_get_candidate_slot_round_trip():
    now = datetime.now(DEMO_TZ) + timedelta(days=1)
    slots = build_candidate_slots(now=now)
    assert slots
    found = get_candidate_slot(slots[0]["slot_id"], now=now)
    assert found is not None
    assert found["slot_id"] == slots[0]["slot_id"]


def test_check_availability_tool():
    ctx = ToolContext(session_id="sess-avail", tenant_id="daves-hvac")
    set_tool_context(ctx)
    try:
        result = json.loads(check_availability.invoke({}))
    finally:
        clear_tool_context()
    assert result["count"] >= 1
    assert "slot_id" in result["slots"][0]
    assert "label" in result["slots"][0]


def test_book_appointment_tool():
    slots = list_open_slots("daves-hvac", limit=1)
    slot_id = slots[0]["slot_id"]
    session_id = str(uuid.uuid4())
    ctx = ToolContext(session_id=session_id, tenant_id="daves-hvac")
    set_tool_context(ctx)
    try:
        result = json.loads(
            book_appointment.invoke(
                {
                    "slot_id": slot_id,
                    "caller_name": "Matteo",
                    "phone": "5125551212",
                    "address": "4005 Amy Circle",
                    "reason": "AC not cooling",
                }
            )
        )
    finally:
        clear_tool_context()

    assert result["booked"] is True
    assert result["slot_id"] == slot_id
    assert get_appointment_for_session(session_id) is not None
