"""Twilio Voice webhooks — ConversationRelay phone demo (menu + agent)."""

from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Callable
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from agents.orchestrator import run_post_call_pipeline
from agents.receptionist import (
    invoke_turn,
    messages_from_serializable,
    messages_to_serializable,
)
from api.twilio_auth import parse_twilio_webhook
from db import (
    get_session_created_at,
    get_session_tenant_id,
    get_tenant,
    load_session_state,
    save_session_state,
)
from scripts.seed import IVR_TENANT_MAP

router = APIRouter(prefix="/twilio/voice", tags=["twilio-voice"])

# ElevenLabs voice for ConversationRelay (tenant greeting + Mira)
MIRA_TTS_VOICE = "tnSpp4vdxKPjI9w0GnoV-flash_v2_5-1.0_0.5_0.8"
IVR_AUDIO_RELATIVE = "assets/ivr-menu.mp3"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_IVR_AUDIO_PATH = _REPO_ROOT / "static" / "ivr-menu.mp3"

GraphFactory = Callable[[], object]
_get_graph: GraphFactory | None = None
_request_base_url: ContextVar[str] = ContextVar("request_base_url", default="")


def configure_voice_routes(get_graph: GraphFactory) -> None:
    global _get_graph
    _get_graph = get_graph


def bind_public_base_url(request: Request) -> None:
    """Prefer MIRA_PUBLIC_URL; otherwise derive from the incoming request (Lambda URL)."""
    env_base = os.environ.get("MIRA_PUBLIC_URL", "").strip().rstrip("/")
    if env_base:
        _request_base_url.set(env_base)
        return
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", "")
    _request_base_url.set(f"{proto}://{host}".rstrip("/") if host else "")


def public_url(path: str) -> str:
    base = _request_base_url.get() or os.environ.get("MIRA_PUBLIC_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "MIRA_PUBLIC_URL is not set. Use ngrok (or your deployed API URL) so Twilio can reach webhooks."
        )
    return urljoin(f"{base}/", path.lstrip("/"))


def conversation_relay_wss_url() -> str:
    url = os.environ.get("CONVERSATION_RELAY_WSS_URL", "").strip()
    if not url:
        raise RuntimeError(
            "CONVERSATION_RELAY_WSS_URL is not set. Deploy the CDK WebSocket API "
            "or set the wss:// URL for ConversationRelay."
        )
    return url


def ivr_audio_url() -> str:
    """Public HTTPS URL Twilio <Play>s for the company menu (same voice when generated via ElevenLabs)."""
    override = os.environ.get("MIRA_IVR_AUDIO_URL", "").strip()
    if override:
        return override
    return public_url(IVR_AUDIO_RELATIVE)


def twiml(response: VoiceResponse) -> Response:
    """Return TwiML with the content type Twilio expects."""
    return Response(content=str(response), media_type="application/xml")


def _voice_response() -> VoiceResponse:
    return VoiceResponse()


def _graph():
    if _get_graph is None:
        raise RuntimeError("Voice routes not configured")
    return _get_graph()


def _run_post_call_if_needed(call_sid: str) -> None:
    tenant_id = get_session_tenant_id(call_sid)
    if not tenant_id:
        return

    prior = load_session_state(call_sid)
    if not prior:
        return

    state, serialized = prior
    if state.get("post_call_done"):
        return

    messages = messages_from_serializable(serialized)
    if not messages:
        return

    started_at = get_session_created_at(call_sid)
    run_post_call_pipeline(
        tenant_id=tenant_id,
        session_id=call_sid,
        messages=messages,
        dialog_state=state,
        started_at=started_at,
    )

    state["post_call_done"] = True
    save_session_state(call_sid, tenant_id, state, serialized)


def _gather_speech(response: VoiceResponse, action_path: str, prompt: str | None = None) -> None:
    """Legacy Gather speech helper — kept for /turn fallback tests."""
    gather = Gather(
        input="speech",
        action=public_url(action_path),
        method="POST",
        speech_timeout="auto",
        language="en-US",
        action_on_empty_result=True,
    )
    if prompt:
        gather.say(prompt, voice="Polly.Joanna")
    response.append(gather)
    response.say("I didn't catch that. Goodbye.", voice="Polly.Joanna")
    response.hangup()


def _gather_ivr_menu(response: VoiceResponse) -> None:
    """Play pre-recorded ElevenLabs menu, then collect a single DTMF digit."""
    gather = Gather(
        num_digits=1,
        action=public_url("/twilio/voice/menu"),
        method="POST",
        timeout=10,
        action_on_empty_result=True,
    )
    gather.play(ivr_audio_url())
    response.append(gather)
    response.say("We didn't receive a selection. Goodbye.", voice="Polly.Joanna")
    response.hangup()


def _connect_conversation_relay(
    response: VoiceResponse,
    *,
    session_id: str,
    welcome_greeting: str,
    tenant_id: str | None = None,
) -> None:
    connect = response.connect(action=public_url("/twilio/voice/relay-action"))
    relay = connect.conversation_relay(
        url=conversation_relay_wss_url(),
        welcome_greeting=welcome_greeting,
        welcome_greeting_interruptible="any",
        tts_provider="ElevenLabs",
        voice=MIRA_TTS_VOICE,
        elevenlabs_text_normalization="on",
        transcription_provider="Deepgram",
        interruptible="any",
        dtmf_detection="true",
        report_input_during_agent_speech="dtmf",
        language="en-US",
    )
    relay.parameter(name="session_id", value=session_id)
    if tenant_id:
        relay.parameter(name="tenant_id", value=tenant_id)


@router.post("/incoming")
async def incoming_call(
    request: Request,
    form: Annotated[dict[str, str], Depends(parse_twilio_webhook)],
) -> Response:
    """New call — play IVR menu (pre-recorded), then wait for 1/2/3."""
    bind_public_base_url(request)
    _ = form["CallSid"]
    response = _voice_response()
    _gather_ivr_menu(response)
    return twiml(response)


@router.post("/menu")
async def ivr_menu(
    request: Request,
    form: Annotated[dict[str, str], Depends(parse_twilio_webhook)],
) -> Response:
    """Map keypad digit to tenant and connect ConversationRelay with tenant greeting."""
    bind_public_base_url(request)
    call_sid = form["CallSid"]
    digits = form.get("Digits", "")
    response = _voice_response()
    tenant_id = IVR_TENANT_MAP.get(digits.strip())
    if not tenant_id:
        response.say("Invalid selection.", voice="Polly.Joanna")
        response.redirect(public_url("/twilio/voice/incoming"), method="POST")
        return twiml(response)

    tenant = get_tenant(tenant_id)
    if not tenant:
        response.say("That demo is unavailable. Goodbye.", voice="Polly.Joanna")
        response.hangup()
        return twiml(response)

    save_session_state(
        call_sid,
        tenant_id,
        {"ivr_complete": True, "voice_call": True},
        [],
    )

    _connect_conversation_relay(
        response,
        session_id=call_sid,
        tenant_id=tenant_id,
        welcome_greeting=tenant["greeting"],
    )
    return twiml(response)


@router.post("/turn")
async def speech_turn(
    request: Request,
    form: Annotated[dict[str, str], Depends(parse_twilio_webhook)],
) -> Response:
    """Legacy Gather speech path — kept for local/fallback testing."""
    bind_public_base_url(request)
    call_sid = form["CallSid"]
    speech_result = form.get("SpeechResult", "")
    response = _voice_response()
    tenant_id = get_session_tenant_id(call_sid)
    if not tenant_id:
        response.redirect(public_url("/twilio/voice/incoming"), method="POST")
        return twiml(response)

    user_text = speech_result.strip()
    if not user_text:
        response.say("Sorry, I didn't hear anything.", voice="Polly.Joanna")
        _gather_speech(response, "/twilio/voice/turn", "Please tell me how I can help.")
        return twiml(response)

    prior = load_session_state(call_sid)
    state = prior[0] if prior else {"ivr_complete": True, "voice_call": True}
    messages = messages_from_serializable(prior[1]) if prior else []

    state, messages, reply = invoke_turn(
        _graph(),
        tenant_id=tenant_id,
        session_id=call_sid,
        user_text=user_text,
        prior_state=state,
        prior_messages=messages,
    )

    save_session_state(
        call_sid,
        tenant_id,
        state,
        messages_to_serializable(messages),
    )

    if state.get("should_end_call"):
        response.say(reply or "Thank you for calling. Goodbye.", voice="Polly.Joanna")
        _run_post_call_if_needed(call_sid)
        response.hangup()
        return twiml(response)

    response.say(reply, voice="Polly.Joanna")
    _gather_speech(response, "/twilio/voice/turn")
    return twiml(response)


@router.post("/relay-action")
async def relay_action(
    form: Annotated[dict[str, str], Depends(parse_twilio_webhook)],
) -> Response:
    """Connect action callback when ConversationRelay session ends."""
    call_sid = form.get("CallSid") or form.get("callSid") or ""
    if call_sid:
        _run_post_call_if_needed(call_sid)
    response = _voice_response()
    response.hangup()
    return twiml(response)


@router.post("/status")
async def call_status(
    form: Annotated[dict[str, str], Depends(parse_twilio_webhook)],
) -> Response:
    """Run post-call pipeline when the phone call ends (configure on Twilio number)."""
    call_sid = form["CallSid"]
    call_status_value = form.get("CallStatus", "")
    if call_status_value in {"completed", "busy", "failed", "no-answer", "canceled"}:
        _run_post_call_if_needed(call_sid)
    return Response(content="", media_type="text/plain")


def ivr_menu_audio_response() -> FileResponse | Response:
    """Serve the pre-recorded IVR menu MP3 for Twilio <Play>."""
    if not _IVR_AUDIO_PATH.is_file():
        return Response(
            content=f"IVR audio missing at {_IVR_AUDIO_PATH}. Run scripts/generate_ivr_audio.py",
            status_code=404,
            media_type="text/plain",
        )
    return FileResponse(
        _IVR_AUDIO_PATH,
        media_type="audio/mpeg",
        filename="ivr-menu.mp3",
    )
