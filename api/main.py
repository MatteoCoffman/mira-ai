"""Optional FastAPI endpoint for Mira — HTTP turns and Twilio Voice."""

from __future__ import annotations

import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from agents.receptionist import (
    build_receptionist_graph,
    invoke_turn,
    messages_from_serializable,
    messages_to_serializable,
)
from api.twilio_voice import configure_voice_routes, router as twilio_voice_router
from db import get_tenant, init_db, load_session_state, save_session_state
from scripts.seed import main as seed_main

app = FastAPI(title="Mira API", version="0.2.0")
_graph = None


class TurnRequest(BaseModel):
    utterance: str
    tenant_id: str = "daves-hvac"
    session_id: str | None = None


class TurnResponse(BaseModel):
    session_id: str
    reply: str
    state: dict
    should_end_call: bool = False


def get_graph():
    if _graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    return _graph


@app.on_event("startup")
def startup() -> None:
    global _graph
    init_db()
    seed_main()
    _graph = build_receptionist_graph()
    configure_voice_routes(lambda: _graph)


app.include_router(twilio_voice_router)


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
