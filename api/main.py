"""Optional FastAPI endpoint for Mira turns."""

from __future__ import annotations

import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from agents.receptionist import (
    build_receptionist_graph,
    invoke_turn,
    messages_from_serializable,
    messages_to_serializable,
)
from db.sqlite import get_tenant, init_db, load_session_state, save_session_state
from scripts.seed import DAVE_HVAC, main as seed_main

app = FastAPI(title="Mira API", version="0.1.0")
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


@app.on_event("startup")
def startup() -> None:
    global _graph
    init_db()
    seed_main()
    _graph = build_receptionist_graph()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "mira-ai"}


@app.post("/turn", response_model=TurnResponse)
def turn(req: TurnRequest) -> TurnResponse:
    if _graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    tenant = get_tenant(req.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {req.tenant_id}")

    session_id = req.session_id or str(uuid.uuid4())
    prior = load_session_state(session_id)
    state = prior[0] if prior else {}
    messages = messages_from_serializable(prior[1]) if prior else []

    state, messages, reply = invoke_turn(
        _graph,
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
