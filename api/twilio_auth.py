"""Twilio webhook signature validation."""

from __future__ import annotations

import os
from urllib.parse import urljoin

from fastapi import HTTPException, Request
from twilio.request_validator import RequestValidator


def signature_validation_enabled() -> bool:
    if os.environ.get("MIRA_VALIDATE_TWILIO_SIGNATURE", "true").lower() == "false":
        return False
    return bool(os.environ.get("TWILIO_AUTH_TOKEN", "").strip())


def webhook_url(request: Request) -> str:
    """Full URL Twilio signed — must match the configured webhook URL."""
    env_base = os.environ.get("MIRA_PUBLIC_URL", "").strip().rstrip("/")
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    if env_base:
        return urljoin(f"{env_base}/", path.lstrip("/"))
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", "")
    return f"{proto}://{host}{path}"


def verify_twilio_signature(request: Request, params: dict[str, str]) -> None:
    if not signature_validation_enabled():
        return

    auth_token = os.environ["TWILIO_AUTH_TOKEN"].strip()
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature")

    url = webhook_url(request)
    if not RequestValidator(auth_token).validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def compute_twilio_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Build X-Twilio-Signature for tests."""
    return RequestValidator(auth_token).compute_signature(url, params)


async def parse_twilio_webhook(request: Request) -> dict[str, str]:
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}
    verify_twilio_signature(request, params)
    return params
