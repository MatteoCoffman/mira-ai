"""Tests for availability and appointment booking."""

from __future__ import annotations

import json
import uuid

import pytest

from agents.tools.book_appointment import book_appointment
from agents.tools.check_availability import check_availability
from agents.tools.context import ToolContext, clear_tool_context, set_tool_context
from db import (
    book_slot,
    get_appointment_for_session,
    get_slot,
    init_db,
    list_open_slots,
    seed_availability_slots,
    seed_tenant,
)
from scripts.seed import DAVE_HVAC, build_availability_slots


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_DB_BACKEND", "sqlite")
    monkeypatch.setenv("MIRA_DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_tenant(DAVE_HVAC)
    seed_availability_slots(DAVE_HVAC["tenant_id"], build_availability_slots())
    yield


def test_build_availability_slots_has_open_weekdays():
    slots = build_availability_slots()
    assert len(slots) >= 4
    assert all(s["status"] == "open" for s in slots)
    assert all("label" in s and "slot_id" in s for s in slots)


def test_list_open_slots_returns_seeded():
    slots = list_open_slots("daves-hvac", limit=3)
    assert len(slots) == 3
    assert slots[0]["starts_at"] <= slots[1]["starts_at"]


def test_book_slot_marks_booked_and_creates_appointment():
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
    assert get_slot("daves-hvac", slot_id)["status"] == "booked"
    assert get_appointment_for_session(session_id)["appointment_id"] == appointment[
        "appointment_id"
    ]


def test_double_book_fails():
    slots = list_open_slots("daves-hvac", limit=1)
    slot_id = slots[0]["slot_id"]
    book_slot("daves-hvac", slot_id, session_id="s1", caller_name="A")
    with pytest.raises(ValueError, match="not available"):
        book_slot("daves-hvac", slot_id, session_id="s2", caller_name="B")


def test_reseed_preserves_booked_slots():
    slots = list_open_slots("daves-hvac", limit=1)
    slot_id = slots[0]["slot_id"]
    book_slot("daves-hvac", slot_id, session_id="s-reseed", caller_name="A")
    assert get_slot("daves-hvac", slot_id)["status"] == "booked"

    seed_availability_slots("daves-hvac", build_availability_slots())

    assert get_slot("daves-hvac", slot_id)["status"] == "booked"
    assert slot_id not in {s["slot_id"] for s in list_open_slots("daves-hvac", limit=20)}


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
