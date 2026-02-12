# MCP Tool Server + Agentic Automation (Production-ish demo)

This project is a small **MCP-like tool server** + **workflow client** that demonstrates how to safely expose operational tools to an “agent” (or automation runner) with **guardrails**:

- ✅ API-key auth
- ✅ Tool allowlist / policy checks
- ✅ Idempotency keys (avoid duplicate “create” actions)
- ✅ Human-in-the-loop (HITL) confirmations for risky actions
- ✅ Audit logging (JSONL event trail)
- ✅ Simple rate limiting per API key
- ✅ Tool discovery endpoint (`/mcp/tools`) with input/output schemas

It’s intentionally **LLM-agnostic**: the focus is on **tooling + safety + ops workflows**, not on model calls.

---

## What it does (in plain terms)

You can run a workflow that:

1) Finds a customer in a simple CRM-like database  
2) Creates a support ticket (**idempotent**, so it won’t create duplicates)  
3) Requests a customer status update (**requires approval**)  
4) Confirms the action (HITL step)  
5) Sends a “support channel” message (mock)  
6) Logs every step to `server/app/audit.log` (JSON lines)

The included demo runs the workflow twice to prove **idempotency replay**.

---

## Project structure

```
.
├─ client/
│  ├─ agent.py            # client wrapper for calling server tools
│  ├─ scenarios.py        # demo workflow (scenario 1 + scenario 2)
│  └─ requirements.txt
├─ server/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py          # FastAPI server + tool endpoints + tool discovery
│  │  ├─ db.py            # SQLAlchemy engine/session + sqlite setup
│  │  ├─ models.py        # Customer, Ticket, PendingAction models
│  │  ├─ policy.py        # allowlist/policy enforcement
│  │  ├─ idempotency.py   # idempotency cache (in-memory)
│  │  └─ audit.py         # JSONL audit logger
│  ├─ requirements.txt
│  └─ .env.example
├─ docker-compose.yml     # optional
└─ README.md
```


## Quickstart (Windows / PowerShell)

### 1) Create venv + install deps (once)

From repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r server\requirements.txt
pip install -r client\requirements.txt
```

If PowerShell blocks activation, run:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2) Run the server (Terminal 1)

```powershell
cd server
..\.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

You should see:  
`Uvicorn running on http://127.0.0.1:8000`


### 3) Run the demo client (Terminal 2)

```powershell
cd client
..\.\.venv\Scripts\Activate.ps1
python scenarios.py
```

Expected behavior:
- Scenario 1 runs the full flow
- Scenario 2 repeats the same request and create_ticket should return idempotent_replay: True


---

## Configuration

Create a file called `server/.env` (do **NOT** commit it).  
Use `server/.env.example` as a template.

Example `server/.env`:

```env
API_KEY=dev-key
ALLOWED_TOOLS=search_customer,create_ticket,update_customer_status,send_message,get_incident_impact
```

> ✅ Tip: Commit `server/.env.example` to GitHub, but never commit `server/.env`.


### What these settings do
- `API_KEY` is the shared key required to call the server.
- `ALLOWED_TOOLS` is an allowlist: tools not listed here will be blocked by policy.

### Auth header
All tool endpoints require the header:

- `X-API-Key: <API_KEY>`

Example (conceptually):

- `X-API-Key: dev-key`

---

## Tools exposed by the server

- `POST /tools/search_customer`
- `POST /tools/create_ticket` (supports `Idempotency-Key`)
- `POST /tools/update_customer_status` (creates `PendingAction` unless `confirm=true`)
- `POST /confirm/{pending_action_id}` (approve/reject)
- `POST /tools/send_message` (mock)
- `POST /tools/get_incident_impact` (placeholder tool)
- `GET /mcp/tools` (tool discovery with schemas)
- `GET /health`


---

## Safety & reliability features


### API key auth
Every call must include `X-API-Key`. Unauthorized requests return `401`.

### Allowlist / policy
Only tools included in `ALLOWED_TOOLS` may be called.

### Idempotency keys
`create_ticket` supports an Idempotency-Key header:
- same key → same response (prevents duplicates)

### Human-in-the-loop (HITL)
Risky actions (like status change) return `requires_confirmation=true` unless explicitly confirmed.
Client can then call `/confirm/{pending_action_id}`.

### Audit log
All tool calls and confirmations are written as JSON lines.

### Rate limiting (basic)
Simple per-key throttling to avoid spam.


---

## Why this matters (interview talking points)

This demo shows:
- how to expose “agent tools” safely (auth + allowlist)
- how to prevent accidental repeated actions (idempotency)
- how to design risk gates (human approval)
- how to create an operational audit trail (logs)
- how to package tools with schemas (tool discovery endpoint)

---

## Next improvements (optional)

- Persist idempotency + pending actions in DB (instead of in-memory)
- Real integrations (Slack/Jira/CRM APIs) behind the same tool interface
- Stronger auth (JWT, per-user keys) + structured RBAC policies
- Better rate limiting (Redis) + request tracing (OpenTelemetry)
- Add a small “graph” query tool to show incident → customer impact
