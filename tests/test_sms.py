"""Tests for owner SMS delivery."""

from __future__ import annotations

import os

from services.sms import resolve_owner_phone, send_owner_sms


def test_resolve_owner_phone_uses_env_override(monkeypatch):
    monkeypatch.setenv("MIRA_OWNER_SMS_PHONE", "+15125551234")
    assert resolve_owner_phone("+15551234567") == "+15125551234"


def test_send_owner_sms_mocks_fake_seed_number(capsys, monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+13616783237")
    monkeypatch.delenv("MIRA_OWNER_SMS_PHONE", raising=False)

    channel = send_owner_sms("+15551234567", "Emergency test")
    assert channel == "mock_sms"
    captured = capsys.readouterr()
    assert "MOCK SMS" in captured.out
