"""Optional FastAPI endpoint for Mira — HTTP turns and Twilio Voice."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from agents.receptionist import (
    build_receptionist_graph,
    invoke_turn,
    messages_from_serializable,
    messages_to_serializable,
)
from api.owner import router as owner_router
from api.twilio_voice import (
    configure_voice_routes,
    ivr_menu_audio_response,
    router as twilio_voice_router,
)
from db import get_tenant, init_db, load_session_state, save_session_state
from scripts.seed import main as seed_main
from services.secrets import load_secrets

app = FastAPI(title="Mira API", version="0.4.0")
_graph = None
_initialized = False


def _cors_origins() -> list[str]:
    raw = os.environ.get("MIRA_CORS_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:3000"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class TurnRequest(BaseModel):
    utterance: str
    tenant_id: str = "daves-hvac"
    session_id: str | None = None


class TurnResponse(BaseModel):
    session_id: str
    reply: str
    state: dict
    should_end_call: bool = False


def _ensure_initialized() -> None:
    global _graph, _initialized
    if _initialized:
        return
    load_secrets()
    init_db()
    seed_main()
    _graph = build_receptionist_graph()
    configure_voice_routes(lambda: _graph)
    _initialized = True


def get_graph():
    _ensure_initialized()
    if _graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    return _graph


@app.middleware("http")
async def initialize_on_request(request: Request, call_next):
    _ensure_initialized()
    return await call_next(request)


app.include_router(twilio_voice_router)
app.include_router(owner_router)


@app.get("/assets/ivr-menu.mp3", include_in_schema=False)
def ivr_menu_audio():
    """Public MP3 for Twilio <Play> during the company menu Gather."""
    return ivr_menu_audio_response()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "mira-ai", "voice": "/twilio/voice/incoming"}


@app.post("/turn", response_model=TurnResponse)
def turn(req: TurnRequest) -> TurnResponse:
    graph = get_graph()

    tenant = get_tenant(req.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {req.tenant_id}")

    session_id = req.session_id or str(uuid.uuid4())
    prior = load_session_state(session_id)
    state = prior[0] if prior else {}
    messages = messages_from_serializable(prior[1]) if prior else []

    state, messages, reply = invoke_turn(
        graph,
        tenant_id=req.tenant_id,
        session_id=session_id,
        user_text=req.utterance,
        prior_state=state,
        prior_messages=messages,
    )

    save_session_state(
        session_id,
        req.tenant_id,
        state,
        messages_to_serializable(messages),
    )

    return TurnResponse(
        session_id=session_id,
        reply=reply,
        state=state,
        should_end_call=state.get("should_end_call", False),
    )
