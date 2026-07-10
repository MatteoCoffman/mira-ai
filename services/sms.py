"""Send owner SMS via Twilio or mock for local dev."""

from __future__ import annotations

import os
import re


def resolve_owner_phone(tenant_phone: str | None) -> str:
    """Demo override via env, else tenant-configured owner phone."""
    override = os.environ.get("MIRA_OWNER_SMS_PHONE", "").strip()
    if override:
        return override
    return (tenant_phone or "unknown").strip()


def _looks_like_fake_number(phone: str) -> bool:
    """Detect seeded demo numbers Twilio will reject (e.g. 555-1234)."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10:
        return True
    # North American reserved 555-01XX exchange used in fiction
    return "55501" in digits[-7:] or digits.endswith("5551234567")


def _mock_send(to_phone: str, body: str, *, reason: str | None = None) -> str:
    prefix = f" ({reason})" if reason else ""
    print(f"\n📱 [MOCK SMS → {to_phone}]{prefix}\n{body}\n")
    return "mock_sms"


def send_owner_sms(to_phone: str, body: str) -> str:
    """Return channel used: twilio_sms or mock_sms. Never raises."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.environ.get("TWILIO_PHONE_NUMBER", "").strip()

    if not (account_sid and auth_token and from_number):
        return _mock_send(to_phone, body)

    if _looks_like_fake_number(to_phone):
        return _mock_send(
            to_phone,
            body,
            reason="demo owner number — set MIRA_OWNER_SMS_PHONE for real SMS",
        )

    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException

        client = Client(account_sid, auth_token)
        client.messages.create(to=to_phone, from_=from_number, body=body)
        return "twilio_sms"
    except Exception as exc:
        return _mock_send(to_phone, body, reason=f"SMS failed: {exc}")
