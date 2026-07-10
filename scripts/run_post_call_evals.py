#!/usr/bin/env python3
"""Run post-call eval scenarios (requires OPENAI_API_KEY)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from agents.orchestrator import run_post_call_pipeline
from db import get_call_record, init_db, upsert_lead
from scripts.seed import main as seed_main

DEFAULT_TENANT = "daves-hvac"
SCENARIOS_PATH = ROOT / "evals" / "post_call_scenarios.yaml"


def messages_from_transcript(lines: list[str]) -> list:
    messages = []
    for line in lines:
        if line.startswith("Caller:"):
            messages.append(HumanMessage(content=line.removeprefix("Caller:").strip()))
        elif line.startswith("Mira:"):
            messages.append(AIMessage(content=line.removeprefix("Mira:").strip()))
    return messages


def run_scenario(scenario: dict) -> dict:
    session_id = str(uuid.uuid4())
    lead = scenario.get("lead", {})
    upsert_lead(session_id, DEFAULT_TENANT, lead)
    messages = messages_from_transcript(scenario.get("transcript_lines", []))
    return run_post_call_pipeline(
        tenant_id=DEFAULT_TENANT,
        session_id=session_id,
        messages=messages,
        dialog_state={"collected": lead},
    )


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY required for post-call evals.")
        return 1

    init_db()
    seed_main()

    with SCENARIOS_PATH.open() as f:
        scenarios = yaml.safe_load(f)

    passed = 0
    failed = 0
    failures_detail: list[str] = []

    print(f"\nRunning {len(scenarios)} post-call eval scenarios...\n")

    for scenario in scenarios:
        sid = scenario["id"]
        result = run_scenario(scenario)
        expect = scenario.get("expect", {})
        record = get_call_record(result.get("call_id", ""))

        ok = True
        if expect.get("record_saved") and not result.get("record_saved"):
            ok = False
            failures_detail.append(f"  FAIL {sid}: record_saved expected True")
        if expect.get("summary_sent") and not result.get("summary_sent"):
            ok = False
            failures_detail.append(f"  FAIL {sid}: summary_sent expected True")
        if expect.get("record_saved") and not record:
            ok = False
            failures_detail.append(f"  FAIL {sid}: no call_records row")

        if ok:
            passed += 1
            print(f"  PASS  {sid}")
        else:
            failed += 1
            print(f"  FAIL  {sid}")

    print(f"\nResults: {passed}/{len(scenarios)} passed, {failed} failed\n")
    for line in failures_detail:
        print(line)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
