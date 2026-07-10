"""Send owner SMS via Twilio or mock for local dev."""

from __future__ import annotations

import os


def send_owner_sms(to_phone: str, body: str) -> str:
    """Return channel used: twilio_sms or mock_sms."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.environ.get("TWILIO_PHONE_NUMBER", "").strip()

    if not (account_sid and auth_token and from_number):
        print(f"\n📱 [MOCK SMS → {to_phone}]\n{body}\n")
        return "mock_sms"

    from twilio.rest import Client

    client = Client(account_sid, auth_token)
    client.messages.create(to=to_phone, from_=from_number, body=body)
    return "twilio_sms"
