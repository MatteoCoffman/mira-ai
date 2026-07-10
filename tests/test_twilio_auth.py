"""Tests for Twilio webhook signature validation."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.twilio_auth import (
    compute_twilio_signature,
    signature_validation_enabled,
    verify_twilio_signature,
    webhook_url,
)

AUTH_TOKEN = "test-auth-token"


def _make_request(
    *,
    path: str = "/twilio/voice/incoming",
    headers: dict[str, str] | None = None,
    body: bytes = b"CallSid=CA-test",
) -> Request:
    merged_headers = {"host": "test.example.com", **(headers or {})}
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "scheme": "https",
        "query_string": b"",
        "headers": [
            (key.lower().encode(), value.encode()) for key, value in merged_headers.items()
        ],
        "client": ("testclient", 50000),
        "server": ("test.example.com", 443),
    }
    request = Request(scope)
    request._body = body  # noqa: SLF001 — test helper
    return request


def test_signature_validation_enabled_respects_env(monkeypatch):
    monkeypatch.delenv("MIRA_VALIDATE_TWILIO_SIGNATURE", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    assert signature_validation_enabled() is False

    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    assert signature_validation_enabled() is True

    monkeypatch.setenv("MIRA_VALIDATE_TWILIO_SIGNATURE", "false")
    assert signature_validation_enabled() is False


def test_webhook_url_uses_public_base(monkeypatch):
    monkeypatch.setenv("MIRA_PUBLIC_URL", "https://test.example.com")
    request = _make_request(path="/twilio/voice/menu")
    assert webhook_url(request) == "https://test.example.com/twilio/voice/menu"


def test_verify_accepts_valid_signature(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("MIRA_PUBLIC_URL", "https://test.example.com")
    params = {"CallSid": "CA-test"}
    url = "https://test.example.com/twilio/voice/incoming"
    signature = compute_twilio_signature(url, params, AUTH_TOKEN)
    request = _make_request(headers={"X-Twilio-Signature": signature})
    verify_twilio_signature(request, params)


def test_verify_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("MIRA_PUBLIC_URL", "https://test.example.com")
    request = _make_request(headers={"X-Twilio-Signature": "bad-signature"})
    with pytest.raises(HTTPException) as exc:
        verify_twilio_signature(request, {"CallSid": "CA-test"})
    assert exc.value.status_code == 403


def test_verify_rejects_missing_signature(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    request = _make_request()
    with pytest.raises(HTTPException) as exc:
        verify_twilio_signature(request, {"CallSid": "CA-test"})
    assert exc.value.status_code == 403
