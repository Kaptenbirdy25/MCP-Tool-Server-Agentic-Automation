from __future__ import annotations

import requests
from typing import Any


class ToolClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}

    def post(self, path: str, json: dict[str, Any], headers: dict[str, str] | None = None):
        h = dict(self.headers)
        if headers:
            h.update(headers)
        r = requests.post(f"{self.base_url}{path}", json=json, headers=h, timeout=30)
        r.raise_for_status()
        return r.json()

    def search_customer(self, query: str):
        return self.post("/tools/search_customer", {"query": query})

    def create_ticket(self, customer_id: int, title: str, description: str, priority: str, idem_key: str | None = None):
        headers = {}
        if idem_key:
            headers["Idempotency-Key"] = idem_key
        return self.post(
            "/tools/create_ticket",
            {"customer_id": customer_id, "title": title, "description": description, "priority": priority},
            headers=headers or None,
        )

    def update_customer_status(self, customer_id: int, new_status: str, confirm: bool = False):
        return self.post("/tools/update_customer_status", {"customer_id": customer_id, "new_status": new_status, "confirm": confirm})

    def confirm(self, pending_action_id: str, approve: bool = True):
        return self.post(f"/confirm/{pending_action_id}", {"approve": approve})

    def send_message(self, channel: str, message: str):
        return self.post("/tools/send_message", {"channel": channel, "message": message})


def run_simple_ops_flow(client: ToolClient, customer_name: str, idem_key: str, auto_approve: bool = True):
    # 1) hitta kund
    res = client.search_customer(customer_name)
    results = res.get("results", [])
    if not results:
        print("Hittade ingen kund som matchar:", customer_name)
        return

    customer = results[0]
    print("Kund:", customer)

    # 2) skapa ticket (idempotent)
    ticket = client.create_ticket(
        customer_id=customer["id"],
        title="Customer reports latency issues",
        description="Customer reports increased latency in the product. Please investigate.",
        priority="high",
        idem_key=idem_key,
    )
    print("Ticket:", ticket)

    # 3) uppdatera status (HITL)
    upd = client.update_customer_status(customer_id=customer["id"], new_status="Investigating", confirm=False)
    if upd.get("requires_confirmation"):
        pending_id = upd["pending_action_id"]
        print("Åtgärd kräver bekräftelse. Pending action:", pending_id)
        if auto_approve:
            conf = client.confirm(pending_id, approve=True)
            print("Auto-bekräftat:", conf)
        else:
            answer = input("Godkänn statusändring? (y/n): ").strip().lower()
            if answer == "y":
                conf = client.confirm(pending_id, approve=True)
                print("Bekräftat:", conf)
            else:
                rej = client.confirm(pending_id, approve=False)
                print("Avböjt:", rej)
    else:
        print("Status uppdaterad direkt:", upd)

    # 4) skicka meddelande (mock)
    msg = client.send_message("#support", f"Created ticket for {customer['name']} and set status to Investigating.")
    print("Meddelande:", msg)
