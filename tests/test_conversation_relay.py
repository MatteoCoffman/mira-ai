"""Tests for ConversationRelay helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.conversation_relay import (
    bind_connection_from_setup,
    chunk_reply_for_tts,
    end_session_message,
    handle_prompt,
    text_token_messages,
)
from db import get_ws_connection, init_db, save_session_state
from scripts.seed import DAVE_HVAC, main as seed_main


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_DB_BACKEND", "sqlite")
    monkeypatch.setenv("MIRA_DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_main()


def test_chunk_reply_for_tts_splits_sentences():
    chunks = chunk_reply_for_tts("Hello there. How can I help?")
    assert chunks == ["Hello there.", "How can I help?"]


def test_text_token_messages_marks_last():
    messages = text_token_messages("One. Two.")
    assert len(messages) == 2
    assert messages[0]["type"] == "text"
    assert messages[0]["last"] is False
    assert messages[1]["last"] is True


def test_end_session_message():
    msg = end_session_message("done")
    assert msg["type"] == "end"
    assert "done" in msg["handoffData"]


def test_bind_connection_from_setup(db):
    bind_connection_from_setup(
        "conn-1",
        {
            "type": "setup",
            "callSid": "CA-setup",
            "customParameters": {
                "tenant_id": DAVE_HVAC["tenant_id"],
                "session_id": "CA-setup",
            },
        },
    )
    conn = get_ws_connection("conn-1")
    assert conn is not None
    assert conn["session_id"] == "CA-setup"
    assert conn["tenant_id"] == "daves-hvac"


def test_handle_prompt_returns_text_tokens(db):
    save_session_state(
        "CA-prompt",
        DAVE_HVAC["tenant_id"],
        {"ivr_complete": True, "voice_call": True},
        [],
    )
    graph = MagicMock()
    with patch("api.conversation_relay.invoke_turn") as mock_turn:
        mock_turn.return_value = (
            {"collected": {}, "should_end_call": False},
            [],
            "We are open Monday through Friday.",
        )
        outbound, state = handle_prompt(
            graph,
            session_id="CA-prompt",
            tenant_id=DAVE_HVAC["tenant_id"],
            voice_prompt="What are your hours?",
        )

    assert outbound[0]["type"] == "text"
    assert "Monday" in outbound[0]["token"] or any(
        "Monday" in m.get("token", "") for m in outbound
    )
    assert state.get("should_end_call") is False
    assert all(m["type"] != "end" for m in outbound)


def test_handle_prompt_ends_session_when_should_end_call(db):
    save_session_state(
        "CA-end",
        DAVE_HVAC["tenant_id"],
        {"ivr_complete": True, "voice_call": True},
        [],
    )
    graph = MagicMock()
    with patch("api.conversation_relay.invoke_turn") as mock_turn:
        mock_turn.return_value = (
            {"should_end_call": True},
            [],
            "Thanks for calling. Goodbye.",
        )
        outbound, _ = handle_prompt(
            graph,
            session_id="CA-end",
            tenant_id=DAVE_HVAC["tenant_id"],
            voice_prompt="That's all",
        )

    assert outbound[-1]["type"] == "end"
