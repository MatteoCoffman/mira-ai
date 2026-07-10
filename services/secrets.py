"""Load API credentials from AWS Secrets Manager at runtime."""

from __future__ import annotations

import json
import os

_loaded = False

_SECRET_KEYS = (
    "OPENAI_API_KEY",
    "LANGCHAIN_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "MIRA_OWNER_SMS_PHONE",
)


def load_secrets() -> None:
    """Merge Secrets Manager JSON into os.environ (local dev uses .env only)."""
    global _loaded
    if _loaded:
        return

    secret_arn = os.environ.get("MIRA_SECRETS_ARN", "").strip()
    if not secret_arn:
        _loaded = True
        return

    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    payload = json.loads(response["SecretString"])

    for key in _SECRET_KEYS:
        value = payload.get(key)
        if value is not None and str(value).strip():
            os.environ[key] = str(value).strip()

    _loaded = True
