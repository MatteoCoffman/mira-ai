# Mira — Managed Inbound Reception Assistant

**Mira answers when you can't.**

Mira is an agentic AI phone receptionist for small trades businesses (HVAC, plumbing, etc.). Week 1 delivers a Python CLI demo with LangGraph orchestration, OpenAI tool calling, SQLite persistence, and eval scenarios.

## Architecture

```mermaid
flowchart TD
    caller[CallerInput_CLI] --> graph[Mira_LangGraph]
    graph --> llm[OpenAI_gpt4o_mini]
    llm -->|tool_calls| tools[ToolNode]
    tools --> lookup[lookup_business]
    tools --> save[save_lead]
    tools --> notify[notify_owner]
    lookup --> db[(SQLite)]
    save --> db
    notify --> mockSms[MockSMS_log]
    tools --> graph
    llm -->|final_reply| caller
    graph --> langsmith[LangSmith_traces]
```

## Stack

| Layer | Choice |
|-------|--------|
| LLM | OpenAI `gpt-4o-mini` |
| Orchestration | LangGraph |
| Observability | LangSmith |
| Data | SQLite |
| Interface | CLI (+ optional FastAPI) |

## Quick start

### 1. Prerequisites

- Python 3.11+
- OpenAI API key

### 2. Setup

```bash
cd mira-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,api]"
cp .env.example .env
# Edit .env and set OPENAI_API_KEY (and optional LangSmith keys)
```

### 3. Seed database

```bash
python scripts/seed.py
```

### 4. Run CLI demo

```bash
python scripts/demo_cli.py
```

Example conversation:

```
Caller: My basement is flooding!
Mira:  [marks urgent, asks for details]

Caller: Mike, 555-1234, 42 Oak Street
Mira:  [saves lead, sends mock SMS to owner]
```

### 5. Run tests

```bash
pytest
```

### 6. Run evals (requires OPENAI_API_KEY)

```bash
python scripts/run_evals.py
```

### 7. Optional API server

```bash
uvicorn api.main:app --reload --port 8000
curl -X POST http://localhost:8000/turn \
  -H "Content-Type: application/json" \
  -d '{"utterance": "What are your hours?"}'
```

## LangSmith

Set in `.env`:

```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key
LANGCHAIN_PROJECT=mira-ai
```

Traces appear at [smith.langchain.com](https://smith.langchain.com) for each agent run.

## Project layout

```
mira-ai/
├── agents/
│   ├── tools/           # lookup_business, save_lead, notify_owner, end_call
│   ├── state.py         # LangGraph state
│   ├── receptionist.py  # Graph definition + invoke helpers
│   └── prompts.py       # Mira system prompt
├── db/sqlite.py         # SQLite schema + queries
├── evals/scenarios.yaml # 10 eval scenarios
├── scripts/
│   ├── seed.py          # Seed Dave's HVAC
│   ├── demo_cli.py      # Interactive demo
│   └── run_evals.py     # Eval runner
├── api/main.py          # Optional FastAPI
└── tests/test_tools.py
```

## Interview talking points

1. **Why LangGraph vs one-shot LLM?** Multi-step tool loops, conditional routing (emergency → notify mid-call), and explicit state beat a single JSON response per turn.

2. **Why tools vs hallucinated actions?** Mira must call `save_lead` and `notify_owner` — the model cannot claim it sent an SMS without the tool running.

3. **How does emergency routing work?** After each tool batch, `sync` reads lead state, detects emergency keywords, and routes to `notify` when urgency is emergency and address is present.

4. **What do evals catch?** Regressions in urgency classification, false emergency notifications, and missing tool calls — checked against DB state, not exact wording.

5. **Week 2 roadmap:** Post-call summarizer agent, Twilio SMS/voice, Next.js demo page, MCP tools, 30+ eval cases.

## Known gaps

Eval scenarios may not all pass on first run — LLM behavior varies. Document failures in eval output and tighten prompts/tools iteratively. FAQ intent detection depends on the model calling `save_lead` with `intent=faq`.

## License

Private — portfolio / interview demo project.
