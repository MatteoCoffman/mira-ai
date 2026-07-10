"""Twilio ConversationRelay WebSocket message helpers."""

from __future__ import annotations

import re
from typing import Any

from agents.receptionist import (
    invoke_turn,
    messages_from_serializable,
    messages_to_serializable,
)
from db import (
    get_session_tenant_id,
    get_tenant,
    get_ws_connection,
    load_session_state,
    put_ws_connection,
    save_session_state,
)
from scripts.seed import IVR_TENANT_MAP

PENDING_TENANT = ""


def chunk_reply_for_tts(reply: str) -> list[str]:
    """Split a full agent reply into sentence-ish chunks for earlier TTS start."""
    text = (reply or "").strip()
    if not text:
        return ["Okay."]
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks = [p.strip() for p in parts if p.strip()]
    return chunks or [text]


def text_token_messages(reply: str, *, interruptible: bool = True) -> list[dict[str, Any]]:
    chunks = chunk_reply_for_tts(reply)
    messages: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        messages.append(
            {
                "type": "text",
                "token": chunk if index == len(chunks) - 1 else f"{chunk} ",
                "last": index == len(chunks) - 1,
                "interruptible": interruptible,
            }
        )
    return messages


def end_session_message(reason: str = "agent_ended_call") -> dict[str, Any]:
    return {
        "type": "end",
        "handoffData": f'{{"reason":"{reason}"}}',
    }


def bind_connection_from_setup(
    connection_id: str,
    setup: dict[str, Any],
) -> dict[str, str]:
    """Persist WebSocket connection → CallSid/tenant mapping from setup message."""
    params = setup.get("customParameters") or {}
    session_id = str(params.get("session_id") or setup.get("callSid") or "").strip()
    tenant_id = str(params.get("tenant_id") or "").strip()
    if not session_id:
        raise ValueError("setup message missing callSid/session_id")
    if not tenant_id:
        tenant_id = get_session_tenant_id(session_id) or PENDING_TENANT

    put_ws_connection(
        connection_id,
        session_id=session_id,
        tenant_id=tenant_id,
    )
    return {"session_id": session_id, "tenant_id": tenant_id}


def handle_dtmf(
    *,
    connection_id: str,
    digit: str,
) -> list[dict[str, Any]]:
    """Bind tenant from IVR digit and return greeting TTS tokens."""
    conn = get_ws_connection(connection_id)
    if not conn:
        return text_token_messages(
            "Sorry, I lost the call connection. Please hang up and try again."
        )

    session_id = conn["session_id"]
    if conn.get("tenant_id"):
        return text_token_messages(
            "You're already connected. How can I help you today?"
        )

    tenant_id = IVR_TENANT_MAP.get((digit or "").strip())
    if not tenant_id:
        return text_token_messages(
            "Invalid selection. Press 1 for Dave's HVAC, 2 for Pest Pros, or 3 for Mike's Plumbing."
        )

    tenant = get_tenant(tenant_id)
    if not tenant:
        return text_token_messages(
            "That demo is unavailable. Please try another selection."
        )

    prior = load_session_state(session_id)
    state = prior[0] if prior else {}
    messages = prior[1] if prior else []
    state = {
        **state,
        "ivr_complete": True,
        "voice_call": True,
    }
    save_session_state(session_id, tenant_id, state, messages)
    put_ws_connection(
        connection_id,
        session_id=session_id,
        tenant_id=tenant_id,
    )
    return text_token_messages(tenant["greeting"])


def handle_prompt(
    graph,
    *,
    session_id: str,
    tenant_id: str,
    voice_prompt: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run one receptionist turn and return outbound ConversationRelay messages + state."""
    if not tenant_id:
        outbound = text_token_messages(
            "Please press 1 for Dave's HVAC, 2 for Pest Pros, or 3 for Mike's Plumbing."
        )
        return outbound, {"ivr_complete": False, "voice_call": True}

    user_text = (voice_prompt or "").strip()
    prior = load_session_state(session_id)
    state = prior[0] if prior else {"ivr_complete": True, "voice_call": True}
    messages = messages_from_serializable(prior[1]) if prior else []

    if not user_text:
        outbound = text_token_messages("Sorry, I didn't catch that. Could you say that again?")
        return outbound, state

    state, messages, reply = invoke_turn(
        graph,
        tenant_id=tenant_id,
        session_id=session_id,
        user_text=user_text,
        prior_state=state,
        prior_messages=messages,
    )
    save_session_state(
        session_id,
        tenant_id,
        state,
        messages_to_serializable(messages),
    )

    outbound = text_token_messages(reply or "Okay.")
    if state.get("should_end_call"):
        outbound.append(end_session_message())
    return outbound, state
