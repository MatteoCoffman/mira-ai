"""API Gateway WebSocket Lambda for Twilio ConversationRelay."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from agents.receptionist import build_receptionist_graph
from api.conversation_relay import (
    bind_connection_from_setup,
    handle_dtmf,
    handle_prompt,
)
from db import delete_ws_connection, get_ws_connection, init_db
from scripts.seed import main as seed_main
from services.secrets import load_secrets

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_graph = None
_initialized = False


def _ensure_initialized() -> None:
    global _graph, _initialized
    if _initialized:
        return
    load_secrets()
    init_db()
    seed_main()
    _graph = build_receptionist_graph()
    _initialized = True


def _get_graph():
    _ensure_initialized()
    if _graph is None:
        raise RuntimeError("Graph not initialized")
    return _graph


def _apigw_client(event: dict[str, Any]):
    domain = event["requestContext"]["domainName"]
    stage = event["requestContext"]["stage"]
    endpoint = os.environ.get("WEBSOCKET_CALLBACK_URL", "").strip()
    if not endpoint:
        endpoint = f"https://{domain}/{stage}"
    return boto3.client("apigatewaymanagementapi", endpoint_url=endpoint)


def _post_json(client, connection_id: str, payload: dict[str, Any]) -> None:
    client.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps(payload).encode("utf-8"),
    )


def _ok(body: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps(body or {"ok": True})}


def _bad(status: int, message: str) -> dict[str, Any]:
    return {"statusCode": status, "body": json.dumps({"error": message})}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    route = event.get("requestContext", {}).get("routeKey", "")
    connection_id = event.get("requestContext", {}).get("connectionId", "")

    if route == "$connect":
        return _ok({"connected": True})

    if route == "$disconnect":
        if connection_id:
            delete_ws_connection(connection_id)
        return _ok({"disconnected": True})

    # $default — ConversationRelay JSON messages
    try:
        _ensure_initialized()
        raw_body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64

            raw_body = base64.b64decode(raw_body).decode("utf-8")
        message = json.loads(raw_body)
    except Exception as exc:
        logger.exception("Invalid WebSocket body: %s", exc)
        return _bad(400, "invalid json")

    msg_type = message.get("type")
    client = _apigw_client(event)

    try:
        if msg_type == "setup":
            bind_connection_from_setup(connection_id, message)
            return _ok({"setup": True})

        if msg_type == "prompt":
            if not message.get("last", True):
                return _ok({"ignored": "partial_prompt"})

            conn = get_ws_connection(connection_id)
            if not conn:
                return _bad(400, "unknown connection")

            outbound, _state = handle_prompt(
                _get_graph(),
                session_id=conn["session_id"],
                tenant_id=conn.get("tenant_id") or "",
                voice_prompt=message.get("voicePrompt", ""),
            )
            for payload in outbound:
                _post_json(client, connection_id, payload)
            return _ok({"prompted": True, "messages": len(outbound)})

        if msg_type == "dtmf":
            digit = str(message.get("digit") or "").strip()
            outbound = handle_dtmf(connection_id=connection_id, digit=digit)
            for payload in outbound:
                _post_json(client, connection_id, payload)
            return _ok({"dtmf": digit, "messages": len(outbound)})

        if msg_type in {"interrupt", "error"}:
            logger.info("ConversationRelay event %s: %s", msg_type, message)
            return _ok({"ignored": msg_type})

        logger.warning("Unknown ConversationRelay message type: %s", msg_type)
        return _ok({"ignored": msg_type})
    except Exception as exc:
        logger.exception("WebSocket handler failed: %s", exc)
        try:
            _post_json(
                client,
                connection_id,
                {
                    "type": "text",
                    "token": "Sorry, I'm having trouble right now. Please try again.",
                    "last": True,
                },
            )
        except Exception:
            logger.exception("Failed to send error TTS")
        return _bad(500, str(exc))
