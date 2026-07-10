# Mira — Managed Inbound Reception Assistant

**Mira answers when you can't.**

Mira is an agentic AI phone receptionist for small trades businesses (HVAC, plumbing, etc.). The foundation delivers a Python CLI demo with LangGraph orchestration, OpenAI tool calling, DynamoDB persistence (via AWS CDK), and eval scenarios. **Iteration 2** adds a multi-agent post-call pipeline.

## Architecture

```mermaid
flowchart TD
    caller[CallerInput_CLI] --> receptionist[Receptionist_graph]
    receptionist -->|call ends| orchestrator[CallOrchestrator]
    orchestrator --> postCall[PostCall_graph]
    postCall --> llm[OpenAI_gpt4o_mini]
    llm -->|tool_calls| tools[ToolNode]
    tools --> saveRecord[save_call_record]
    tools --> sendSummary[send_call_summary]
    saveRecord --> db[(DynamoDB)]
    sendSummary --> notify[MockSMS]
    receptionist --> db
    cdk[CDK_deploy] --> db
```

### Agent 1 — Receptionist (live call)

- LangGraph loop: `agent → tools → sync → notify → agent`
- Tools: `lookup_business`, `save_lead`, `end_call`
- Supervisor routes emergency + address to owner alert

### Agent 2 — Post-call (after hang-up)

- LangGraph loop: `agent → tools → sync → agent`
- Tools: `save_call_record`, `send_call_summary`
- Saves transcript + summary to `call_records`, sends owner follow-up SMS

## Stack

| Layer | Choice |
|-------|--------|
| LLM | OpenAI `gpt-4o-mini` |
| Orchestration | LangGraph |
| Observability | LangSmith |
| Data | DynamoDB (CDK-provisioned) |
| Infra | AWS CDK (TypeScript) — Lambda Function URL + API Gateway WebSocket |
| Interface | CLI + FastAPI + Twilio Voice (ConversationRelay) |

## Phone demo (Twilio Voice + ConversationRelay)

Call a real phone number and talk to Mira with streaming speech (Deepgram STT + ElevenLabs TTS via Twilio ConversationRelay). One Twilio number serves three demo businesses via IVR:

| Keypad | Business |
|--------|----------|
| 1 | Dave's HVAC |
| 2 | Pest Pros |
| 3 | Mike's Plumbing |

**Call flow:** IVR digit Gather → `<Connect><ConversationRelay>` WebSocket → LangGraph turns as text tokens → hang-up runs post-call.

### Setup

1. **Twilio account** — [twilio.com](https://www.twilio.com): buy a voice-capable phone number.
2. **Enable ConversationRelay** — complete Twilio's ConversationRelay onboarding / AI-ML addendum in Console (required; Connect fails without it).
3. **Env vars** in `.env`:

```bash
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...
# Optional locally; CDK injects CONVERSATION_RELAY_WSS_URL on deploy
```

4. **Deploy with CDK** (recommended for phone demos — ConversationRelay needs a public `wss://` URL):

```bash
# .env must include OPENAI_API_KEY, Twilio vars, etc.
cd infra
npm install
npm run deploy
# copy ApiFunctionUrl from stack outputs → Twilio webhooks (step 5)
# ConversationRelayWssUrl is injected into the HTTP Lambda automatically
```

Local uvicorn + ngrok HTTP alone is **not enough** for ConversationRelay (WebSocket must be public). Prefer the deployed stack for live calls.

5. **Twilio Console** → Phone Numbers → your number → Voice configuration:
   - **A call comes in:** Webhook `POST` → `{ApiFunctionUrl}twilio/voice/incoming`
   - **Call status changes:** Webhook `POST` → `{ApiFunctionUrl}twilio/voice/status` (runs post-call on hang-up)

6. Call your Twilio number → press 1/2/3 → speak naturally (you can interrupt Mira mid-sentence).

On hang-up, the post-call agent saves the record and sends an owner SMS (real Twilio SMS when credentials are set; mock print otherwise).

**Note:** ConversationRelay + ElevenLabs + Deepgram costs more per minute than Polly — fine for demos; watch usage if the number is public.

## Quick start (CLI)

### 1. Deploy infrastructure (one-time)

Requires AWS CLI credentials and Node.js. CDK reads secrets from the repo-root `.env` at deploy time. The deploy script builds a Linux Lambda bundle automatically (no Docker required).

```bash
aws sts get-caller-identity
cp .env.example .env   # fill in OPENAI_API_KEY, Twilio vars, etc.

cd infra
npm install
npx cdk bootstrap    # once per account/region
npm run deploy       # builds lambda_bundle + deploys stack
cd ..
```

This creates DynamoDB tables (including `mira-ws-connections`), an HTTP Lambda Function URL for Twilio webhooks, and an API Gateway WebSocket for ConversationRelay. Stack outputs: `ApiFunctionUrl`, `ConversationRelayWssUrl`, `ApiSecretArn`. Credentials from `.env` are written to Secrets Manager at deploy time.

### 2. Run the app

```bash
cd mira-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,api]"
cp .env.example .env
# Set OPENAI_API_KEY and optional LangSmith keys
python scripts/seed.py
python scripts/demo_cli.py
```

Example emergency call:

```
Caller: My basement is flooding!
Caller: Mike, 555-1234, 42 Oak Street
```

On `quit` or when Mira ends the call, the **post-call agent** runs automatically.

### SQLite (offline / tests only)

Tests use SQLite automatically. For local offline dev without AWS:

```bash
MIRA_DB_BACKEND=sqlite python scripts/seed.py
MIRA_DB_BACKEND=sqlite python scripts/demo_cli.py
```

## Tests and evals

```bash
pytest   # uses SQLite — no AWS required
python scripts/run_evals.py           # receptionist scenarios
python scripts/run_post_call_evals.py # post-call scenarios
```

## LangSmith

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key
LANGCHAIN_PROJECT=mira-ai
```

Traces appear for both receptionist and post-call graphs at [smith.langchain.com](https://smith.langchain.com).

## Project layout

```
mira-ai/
├── agents/
│   ├── receptionist.py   # Live call agent
│   ├── post_call.py      # Post-call summarizer agent
│   ├── orchestrator.py   # Wires call end → post-call
│   └── tools/
├── db/
│   ├── __init__.py       # Backend router (dynamodb | sqlite)
│   ├── dynamodb.py
│   └── sqlite.py         # Test / offline fallback
├── infra/                # AWS CDK — DynamoDB + HTTP Lambda + ConversationRelay WebSocket
│   ├── bin/app.ts
│   └── lib/mira-stack.ts
├── Dockerfile.lambda     # Optional container image (if you prefer Docker deploy)
├── evals/
│   ├── scenarios.yaml
│   └── post_call_scenarios.yaml
├── scripts/
│   ├── demo_cli.py
│   ├── run_evals.py
│   └── run_post_call_evals.py
└── api/
    ├── main.py
    ├── twilio_voice.py       # IVR + Connect ConversationRelay
    ├── conversation_relay.py # Prompt → text token helpers
    └── ws_handler.py         # API Gateway WebSocket Lambda
```

## Interview talking points

1. **Multi-agent pipeline:** Receptionist handles live turns; post-call agent summarizes and persists after hang-up.
2. **Why LangGraph:** Tool loops, conditional emergency routing, separate graphs per agent role.
3. **Why tools:** Lead save and owner SMS are real function calls — not hallucinated actions.
4. **Supervisor pattern:** Mid-call emergency notify is code-enforced, not left to the LLM alone.
5. **Infrastructure as code:** DynamoDB + Lambda Function URL + ConversationRelay WebSocket via CDK; credentials in Secrets Manager; Twilio webhooks validated via `X-Twilio-Signature`.
6. **Evals:** Separate YAML suites for live-call behavior and post-call summarization.

## Security

- **Twilio webhooks:** Every `/twilio/voice/*` HTTP route validates `X-Twilio-Signature` using your auth token (disable locally with `MIRA_VALIDATE_TWILIO_SIGNATURE=false`).
- **Secrets:** CDK stores OpenAI/Twilio/LangSmith keys in AWS Secrets Manager (`mira/api`). Lambda loads them at cold start via `MIRA_SECRETS_ARN` — not plain env vars in the console.
- **Voice:** After IVR, calls use Twilio ConversationRelay (ElevenLabs TTS + Deepgram STT) over a private WebSocket to your API Gateway stage.

## Roadmap (next iterations)

| Iteration | Focus |
|-----------|--------|
| 3 | Expanded evals + LangSmith eval integration |
| 4 | Owner dashboard (recent calls + notifications) |
| 5 | Cold start optimization + CI |

## License

Portfolio / interview demo project.
