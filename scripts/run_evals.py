#!/usr/bin/env python3
"""Run YAML eval scenarios against Mira."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from agents.receptionist import build_receptionist_graph, invoke_turn
from db.sqlite import count_notifications, get_lead, init_db, get_tool_calls
from scripts.seed import main as seed_main

DEFAULT_TENANT = "daves-hvac"
SCENARIOS_PATH = ROOT / "evals" / "scenarios.yaml"


def run_scenario(graph, scenario: dict) -> dict:
    session_id = str(uuid.uuid4())
    state: dict = {}
    messages: list = []

    for turn in scenario.get("turns", []):
        state, messages, _reply = invoke_turn(
            graph,
            tenant_id=DEFAULT_TENANT,
            session_id=session_id,
            user_text=turn,
            prior_state=state,
            prior_messages=messages,
        )

    lead = get_lead(session_id) or {}
    tool_calls = get_tool_calls(session_id)
    notify_count = count_notifications(session_id)

    return {
        "session_id": session_id,
        "state": state,
        "lead": lead,
        "tool_calls": tool_calls,
        "notify_called": notify_count > 0 or "notify_owner" in tool_calls,
    }


def check_expectations(result: dict, expect: dict) -> list[str]:
    failures = []
    state = result["state"]
    lead = result["lead"]

    if "urgency" in expect:
        actual = lead.get("urgency") or state.get("urgency")
        if actual != expect["urgency"]:
            failures.append(f"urgency: expected {expect['urgency']}, got {actual}")

    if "escalate" in expect:
        if state.get("escalate") != expect["escalate"]:
            failures.append(f"escalate: expected {expect['escalate']}, got {state.get('escalate')}")

    if "intent" in expect:
        actual = lead.get("intent") or state.get("intent")
        if actual != expect["intent"]:
            failures.append(f"intent: expected {expect['intent']}, got {actual}")

    if "should_end_call" in expect:
        if state.get("should_end_call") != expect["should_end_call"]:
            failures.append(
                f"should_end_call: expected {expect['should_end_call']}, got {state.get('should_end_call')}"
            )

    if "notify_called" in expect:
        if result["notify_called"] != expect["notify_called"]:
            failures.append(
                f"notify_called: expected {expect['notify_called']}, got {result['notify_called']}"
            )

    return failures


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY required for evals.")
        return 1

    init_db()
    seed_main()

    with SCENARIOS_PATH.open() as f:
        scenarios = yaml.safe_load(f)

    graph = build_receptionist_graph()
    passed = 0
    failed = 0
    failures_detail: list[str] = []

    print(f"\nRunning {len(scenarios)} eval scenarios...\n")

    for scenario in scenarios:
        sid = scenario["id"]
        result = run_scenario(graph, scenario)
        failures = check_expectations(result, scenario.get("expect", {}))

        if failures:
            failed += 1
            failures_detail.append(f"  FAIL {sid}: " + "; ".join(failures))
            print(f"  FAIL  {sid}")
        else:
            passed += 1
            print(f"  PASS  {sid}")

    print(f"\nResults: {passed}/{len(scenarios)} passed, {failed} failed\n")
    if failures_detail:
        print("Known gaps / failures:")
        for line in failures_detail:
            print(line)
        print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
