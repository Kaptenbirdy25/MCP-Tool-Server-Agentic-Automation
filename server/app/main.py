from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import time
from collections import defaultdict, deque


from .db import SessionLocal, engine
from .models import Base, Customer, Ticket, PendingAction
from .policy import assert_allowed
from .audit import log_event
from .idempotency import get_cached_response, store_response

load_dotenv()  # laddar server/.env om den finns

API_KEY = os.getenv("API_KEY", "dev-key")

# ---- Simple in-memory rate limiting (per API key) ----
RATE_LIMIT_PER_MIN = 60  # justera vid behov
_request_times: dict[str, deque[float]] = defaultdict(deque)

app = FastAPI(title="MCP Tool Server (v1)", version="0.1.0")


# ---------- DB setup ----------
Base.metadata.create_all(bind=engine)

def seed_if_empty(db: Session) -> None:
    if db.query(Customer).count() == 0:
        db.add_all([
            Customer(name="ACME AB", status="Active"),
            Customer(name="Nordic Widgets", status="Active"),
            Customer(name="Beta Logistics", status="Active"),
        ])
        db.commit()

def get_db():
    db = SessionLocal()
    try:
        seed_if_empty(db)
        yield db
    finally:
        db.close()


# ---------- Auth ----------
def require_api_key(x_api_key: str = Header(default="")) -> None:
    # Auth
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    # Rate limit (sliding window 60s)
    now = time.time()
    window = 60.0
    q = _request_times[x_api_key]

    while q and (now - q[0]) > window:
        q.popleft()

    if len(q) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    q.append(now)



# ---------- Schemas ----------
class SearchCustomerIn(BaseModel):
    query: str = Field(..., min_length=1)

class SearchCustomerOut(BaseModel):
    results: list[dict[str, Any]]

class CreateTicketIn(BaseModel):
    customer_id: int
    title: str = Field(..., min_length=3)
    description: str = ""
    priority: str = Field(default="medium")

class CreateTicketOut(BaseModel):
    ticket: dict[str, Any]
    idempotent_replay: bool = False

class UpdateCustomerStatusIn(BaseModel):
    customer_id: int
    new_status: str = Field(..., min_length=2)
    confirm: bool = False  # human-in-the-loop

class UpdateCustomerStatusOut(BaseModel):
    requires_confirmation: bool
    pending_action_id: Optional[str] = None
    customer: Optional[dict[str, Any]] = None

class ConfirmIn(BaseModel):
    approve: bool = True  # true=confirm, false=reject

class SendMessageIn(BaseModel):
    channel: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)

class SendMessageOut(BaseModel):
    sent: bool
    channel: str

# (Liten placeholder för “knowledge graph/relations” senare)
class GetIncidentImpactIn(BaseModel):
    incident_id: str

class GetIncidentImpactOut(BaseModel):
    incident_id: str
    affected_customers: list[dict[str, Any]]




# ---- Tool registry (MCP-like discovery) ----
TOOL_REGISTRY = {
    "search_customer": {
        "path": "/tools/search_customer",
        "method": "POST",
        "description": "Search customers by name substring.",
        "input_model": SearchCustomerIn,
        "output_model": SearchCustomerOut,
        "idempotency": False,
        "risk": "low",
    },
    "create_ticket": {
        "path": "/tools/create_ticket",
        "method": "POST",
        "description": "Create a ticket for a customer. Supports Idempotency-Key header.",
        "input_model": CreateTicketIn,
        "output_model": CreateTicketOut,
        "idempotency": True,
        "risk": "medium",
    },
    "update_customer_status": {
        "path": "/tools/update_customer_status",
        "method": "POST",
        "description": "Update a customer's status. Uses human-in-the-loop unless confirm=true.",
        "input_model": UpdateCustomerStatusIn,
        "output_model": UpdateCustomerStatusOut,
        "idempotency": False,
        "risk": "high",
    },
    "send_message": {
        "path": "/tools/send_message",
        "method": "POST",
        "description": "Send a message to a channel (mock).",
        "input_model": SendMessageIn,
        "output_model": SendMessageOut,
        "idempotency": False,
        "risk": "low",
    },
    "get_incident_impact": {
        "path": "/tools/get_incident_impact",
        "method": "POST",
        "description": "Get which customers are affected by an incident (placeholder).",
        "input_model": GetIncidentImpactIn,
        "output_model": GetIncidentImpactOut,
        "idempotency": False,
        "risk": "low",
    },
}


# ---------- Helpers ----------
def tool_guard(tool: str) -> None:
    try:
        assert_allowed(tool)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ---------- Tools ----------
@app.post("/tools/search_customer", response_model=SearchCustomerOut, dependencies=[Depends(require_api_key)])
def search_customer(payload: SearchCustomerIn, db: Session = Depends(get_db)):
    tool = "search_customer"
    tool_guard(tool)

    q = payload.query.strip().lower()
    rows = db.query(Customer).all()
    matches = [c for c in rows if q in c.name.lower()]

    out = {"results": [{"id": c.id, "name": c.name, "status": c.status} for c in matches]}
    log_event({"tool": tool, "input": payload.model_dump(), "output": {"count": len(matches)}})
    return out


@app.post("/tools/create_ticket", response_model=CreateTicketOut, dependencies=[Depends(require_api_key)])
def create_ticket(
    payload: CreateTicketIn,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    tool = "create_ticket"
    tool_guard(tool)

    # Idempotency replay
    if idempotency_key:
        cached = get_cached_response(db, tool=tool, key=idempotency_key)
        if cached is not None:
            log_event({"tool": tool, "idempotency_replay": True, "key": idempotency_key})
            return {**cached, "idempotent_replay": True}

    cust = db.query(Customer).filter_by(id=payload.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    t = Ticket(
        customer_id=payload.customer_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        priority=payload.priority.strip().lower(),
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    response = {
        "ticket": {
            "id": t.id,
            "customer_id": t.customer_id,
            "title": t.title,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() + "Z",
        }
    }

    if idempotency_key:
        store_response(db, tool=tool, key=idempotency_key, response=response)

    log_event({"tool": tool, "input": payload.model_dump(), "output": {"ticket_id": t.id}})
    return {**response, "idempotent_replay": False}


@app.post("/tools/update_customer_status", response_model=UpdateCustomerStatusOut, dependencies=[Depends(require_api_key)])
def update_customer_status(payload: UpdateCustomerStatusIn, db: Session = Depends(get_db)):
    tool = "update_customer_status"
    tool_guard(tool)

    cust = db.query(Customer).filter_by(id=payload.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Human-in-the-loop: kräver confirm
    if not payload.confirm:
        pending_id = uuid.uuid4().hex
        pa = PendingAction(
            id=pending_id,
            action_type="update_customer_status",
            payload_json=PendingAction.dumps(payload.model_dump()),
            status="pending",
        )
        db.add(pa)
        db.commit()

        log_event({
            "tool": tool,
            "input": payload.model_dump(),
            "output": {"requires_confirmation": True, "pending_action_id": pending_id},
        })
        return {"requires_confirmation": True, "pending_action_id": pending_id, "customer": None}

    # Om confirm=True kör vi direkt
    cust.status = payload.new_status.strip()
    db.commit()
    db.refresh(cust)

    log_event({"tool": tool, "input": payload.model_dump(), "output": {"customer_id": cust.id, "status": cust.status}})
    return {
        "requires_confirmation": False,
        "pending_action_id": None,
        "customer": {"id": cust.id, "name": cust.name, "status": cust.status},
    }


@app.post("/confirm/{pending_action_id}", dependencies=[Depends(require_api_key)])
def confirm_action(pending_action_id: str, payload: ConfirmIn, db: Session = Depends(get_db)):
    tool = "confirm"
    pa = db.query(PendingAction).filter_by(id=pending_action_id).first()
    if not pa:
        raise HTTPException(status_code=404, detail="Pending action not found")
    if pa.status != "pending":
        raise HTTPException(status_code=409, detail=f"Pending action already {pa.status}")

    if not payload.approve:
        pa.status = "rejected"
        db.commit()
        log_event({"tool": tool, "pending_action_id": pending_action_id, "result": "rejected"})
        return {"ok": True, "status": "rejected"}

    # Approve: utför den sparade åtgärden
    data = PendingAction.loads(pa.payload_json)
    if pa.action_type == "update_customer_status":
        cust = db.query(Customer).filter_by(id=data["customer_id"]).first()
        if not cust:
            pa.status = "rejected"
            db.commit()
            raise HTTPException(status_code=404, detail="Customer not found during confirm")

        cust.status = data["new_status"].strip()
        pa.status = "confirmed"
        db.commit()
        db.refresh(cust)

        log_event({"tool": tool, "pending_action_id": pending_action_id, "result": "confirmed", "customer_id": cust.id})
        return {"ok": True, "status": "confirmed", "customer": {"id": cust.id, "name": cust.name, "status": cust.status}}

    pa.status = "rejected"
    db.commit()
    raise HTTPException(status_code=400, detail=f"Unknown action_type: {pa.action_type}")


@app.post("/tools/send_message", response_model=SendMessageOut, dependencies=[Depends(require_api_key)])
def send_message(payload: SendMessageIn):
    tool = "send_message"
    tool_guard(tool)

    # Mock: “skickat” och loggat
    log_event({"tool": tool, "input": payload.model_dump(), "output": {"sent": True}})
    return {"sent": True, "channel": payload.channel}


@app.post("/tools/get_incident_impact", response_model=GetIncidentImpactOut, dependencies=[Depends(require_api_key)])
def get_incident_impact(payload: GetIncidentImpactIn, db: Session = Depends(get_db)):
    tool = "get_incident_impact"
    tool_guard(tool)

    # Placeholder idag: returnerar alla kunder som “affected”
    customers = db.query(Customer).all()
    out = {
        "incident_id": payload.incident_id,
        "affected_customers": [{"id": c.id, "name": c.name, "status": c.status} for c in customers],
    }
    log_event({"tool": tool, "input": payload.model_dump(), "output": {"count": len(customers)}})
    return out


@app.get("/health")
def health():
    return {"ok": True, "version": app.version}

@app.get("/mcp/tools", dependencies=[Depends(require_api_key)])
def list_tools():
    """
    MCP-like tool discovery endpoint.
    Returns tools + JSON schema for inputs/outputs.
    """
    tools = []
    for name, meta in TOOL_REGISTRY.items():
        tools.append({
            "name": name,
            "method": meta["method"],
            "path": meta["path"],
            "description": meta["description"],
            "risk": meta["risk"],
            "supports_idempotency_key": meta["idempotency"],
            "input_schema": meta["input_model"].model_json_schema(),
            "output_schema": meta["output_model"].model_json_schema(),
        })
    return {"tools": tools}
