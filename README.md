# Projekt 2 — MCP Tool Server + Agentic Automation (v1)

## What it does
A small tool server (MCP-like) exposing allowlisted tools to an agent:
- search_customer
- create_ticket (idempotency)
- update_customer_status (human-in-the-loop confirmation)
- send_message (mock)
- get_incident_impact (placeholder)

## Safety features
- API key auth (X-API-Key)
- Tool allowlist (ALLOWED_TOOLS)
- Idempotency keys for create_ticket (Idempotency-Key)
- Human approval flow for risky actions (confirm endpoint)
- JSON audit log (server/app/audit.log)

## Run
### Server
1. Create `server/.env` from `.env.example`
2. Install deps in venv, then run:
   `uvicorn app.main:app --reload --port 8000`

### Client
Run:
`py scenarios.py`
