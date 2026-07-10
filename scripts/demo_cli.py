#!/usr/bin/env python3
"""Interactive CLI demo — fake phone call with Mira."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from agents.orchestrator import build_transcript, run_post_call_pipeline
from agents.receptionist import (
    build_receptionist_graph,
    invoke_turn,
    messages_from_serializable,
    messages_to_serializable,
)
from db import get_tenant, init_db, load_session_state, save_session_state
from scripts.seed import DAVE_HVAC, main as seed_main


DEFAULT_TENANT = "daves-hvac"


def _run_post_call(session_id: str, state: dict, messages: list) -> None:
    print("\n--- Post-call agent ---")
    result = run_post_call_pipeline(
        tenant_id=DEFAULT_TENANT,
        session_id=session_id,
        messages=messages,
        dialog_state=state,
    )
    if result.get("skipped"):
        print(f"Post-call skipped: {result.get('reason')}")
        return
    print(f"Post-call: record_saved={result.get('record_saved')} summary_sent={result.get('summary_sent')}")
    if result.get("summary"):
        print(f"Summary: {result['summary']}\n")


def print_banner() -> None:
    print("\n" + "=" * 60)
    print("  Mira — Managed Inbound Reception Assistant")
    print("  Demo CLI (type caller messages; 'quit' to exit)")
    print("=" * 60 + "\n")


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Set it in .env before running.")

    init_db()
    seed_main()

    tenant = get_tenant(DEFAULT_TENANT)
    if not tenant:
        print(f"Tenant {DEFAULT_TENANT} not found.")
        sys.exit(1)

    session_id = os.environ.get("MIRA_SESSION_ID") or str(uuid.uuid4())
    print(f"Session: {session_id}")
    print(f"Business: {tenant['business_name']}")
    print(f"\nMira: {tenant['greeting']}\n")

    graph = build_receptionist_graph()
    prior = load_session_state(session_id)
    state = prior[0] if prior else {}
    messages = messages_from_serializable(prior[1]) if prior else []

    while True:
        try:
            user_text = input("Caller: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            _run_post_call(session_id, state, messages)
            break

        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit", "q"}:
            print("Call ended.")
            _run_post_call(session_id, state, messages)
            break

        state, messages, reply = invoke_turn(
            graph,
            tenant_id=DEFAULT_TENANT,
            session_id=session_id,
            user_text=user_text,
            prior_state=state,
            prior_messages=messages,
        )

        save_session_state(
            session_id,
            DEFAULT_TENANT,
            state,
            messages_to_serializable(messages),
        )

        print(f"\nMira: {reply}\n")
        print(
            f"  [state] urgency={state.get('urgency')} escalate={state.get('escalate')} "
            f"notified={state.get('owner_notified')} end={state.get('should_end_call')}"
        )
        print(f"  [collected] {state.get('collected', {})}\n")

        if state.get("should_end_call"):
            print("Mira ended the call.")
            _run_post_call(session_id, state, messages)
            break


if __name__ == "__main__":
    print_banner()
    main()
