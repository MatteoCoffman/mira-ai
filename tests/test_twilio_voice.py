"""Tests for Twilio Voice webhook routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agents.receptionist import messages_to_serializable
from db import get_session_tenant_id, init_db, save_session_state
from langchain_core.messages import HumanMessage
from scripts.seed import DAVE_HVAC, main as seed_main


@pytest.fixture
def voice_client(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_DB_BACKEND", "sqlite")
    monkeypatch.setenv("MIRA_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MIRA_PUBLIC_URL", "https://test.example.com")
    monkeypatch.setenv("CONVERSATION_RELAY_WSS_URL", "wss://test.example.com/prod")
    monkeypatch.setenv("MIRA_VALIDATE_TWILIO_SIGNATURE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    mock_graph = MagicMock()
    with patch("api.main.build_receptionist_graph", return_value=mock_graph):
        from api.main import app

        init_db()
        seed_main()
        with TestClient(app) as client:
            yield client, mock_graph


def test_incoming_plays_ivr_and_gathers_digit(voice_client):
    client, _ = voice_client
    response = client.post(
        "/twilio/voice/incoming",
        data={"CallSid": "CA-test-incoming"},
    )
    assert response.status_code == 200
    assert "application/xml" in response.headers.get("content-type", "")
    body = response.text
    assert "Gather" in body
    assert "Play" in body
    assert "assets/ivr-menu.mp3" in body
    assert "/twilio/voice/menu" in body
    assert "ConversationRelay" not in body
    assert "Connect" not in body


def test_menu_connects_conversation_relay_for_valid_digit(voice_client):
    client, _ = voice_client
    response = client.post(
        "/twilio/voice/menu",
        data={"CallSid": "CA-test-menu", "Digits": "1"},
    )
    assert response.status_code == 200
    body = response.text
    assert "ConversationRelay" in body
    assert "Connect" in body
    assert "wss://test.example.com/prod" in body
    assert "ElevenLabs" in body
    assert "tnSpp4vdxKPjI9w0GnoV" in body
    assert "Deepgram" in body
    assert "session_id" in body
    assert "tenant_id" in body
    assert "relay-action" in body
    assert "Dave" in body or "HVAC" in body
    assert get_session_tenant_id("CA-test-menu") == DAVE_HVAC["tenant_id"]


def test_menu_rejects_invalid_digit(voice_client):
    client, _ = voice_client
    response = client.post(
        "/twilio/voice/menu",
        data={"CallSid": "CA-test-bad", "Digits": "9"},
    )
    assert response.status_code == 200
    assert "Invalid selection" in response.text
    assert "/twilio/voice/incoming" in response.text
    assert get_session_tenant_id("CA-test-bad") is None


def test_ivr_audio_asset_served_when_present(voice_client, tmp_path, monkeypatch):
    client, _ = voice_client
    audio_path = Path(__file__).resolve().parents[1] / "static" / "ivr-menu.mp3"
    if not audio_path.is_file():
        pytest.skip("static/ivr-menu.mp3 not generated yet")
    response = client.get("/assets/ivr-menu.mp3")
    assert response.status_code == 200
    assert "audio/mpeg" in response.headers.get("content-type", "")
    assert response.content[:3] == b"ID3" or response.content[:2] == b"\xff\xfb" or len(response.content) > 100


def test_turn_invokes_agent_and_responds(voice_client):
    client, mock_graph = voice_client
    save_session_state(
        "CA-test-turn",
        DAVE_HVAC["tenant_id"],
        {"ivr_complete": True},
        messages_to_serializable([]),
    )

    with patch("api.twilio_voice.invoke_turn") as mock_turn:
        mock_turn.return_value = (
            {"collected": {}},
            [],
            "We are open Monday through Friday.",
        )
        response = client.post(
            "/twilio/voice/turn",
            data={"CallSid": "CA-test-turn", "SpeechResult": "What are your hours?"},
        )

    assert response.status_code == 200
    assert "Monday through Friday" in response.text
    mock_turn.assert_called_once()
    assert mock_graph is not None


def test_relay_action_runs_post_call(voice_client):
    client, _ = voice_client
    save_session_state(
        "CA-test-relay-action",
        DAVE_HVAC["tenant_id"],
        {"ivr_complete": True},
        messages_to_serializable([HumanMessage(content="Need AC repair")]),
    )

    with patch("api.twilio_voice.run_post_call_pipeline") as mock_post:
        mock_post.return_value = {"record_saved": True, "summary_sent": True}
        response = client.post(
            "/twilio/voice/relay-action",
            data={"CallSid": "CA-test-relay-action"},
        )
        assert response.status_code == 200
        assert "Hangup" in response.text
        mock_post.assert_called_once()


def test_status_runs_post_call_once(voice_client):
    client, _ = voice_client
    save_session_state(
        "CA-test-status",
        DAVE_HVAC["tenant_id"],
        {"ivr_complete": True},
        messages_to_serializable([HumanMessage(content="My basement is flooding!")]),
    )

    with patch("api.twilio_voice.run_post_call_pipeline") as mock_post:
        mock_post.return_value = {"record_saved": True, "summary_sent": True}
        response = client.post(
            "/twilio/voice/status",
            data={"CallSid": "CA-test-status", "CallStatus": "completed"},
        )
        assert response.status_code == 200
        mock_post.assert_called_once()

        mock_post.reset_mock()
        client.post(
            "/twilio/voice/status",
            data={"CallSid": "CA-test-status", "CallStatus": "completed"},
        )
        mock_post.assert_not_called()


def test_rejects_unsigned_webhook_when_validation_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_DB_BACKEND", "sqlite")
    monkeypatch.setenv("MIRA_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MIRA_PUBLIC_URL", "https://test.example.com")
    monkeypatch.setenv("MIRA_VALIDATE_TWILIO_SIGNATURE", "true")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-auth-token")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    mock_graph = MagicMock()
    with patch("api.main.build_receptionist_graph", return_value=mock_graph):
        from api.main import app

        init_db()
        seed_main()
        with TestClient(app) as client:
            response = client.post(
                "/twilio/voice/incoming",
                data={"CallSid": "CA-unsigned"},
            )

    assert response.status_code == 403
