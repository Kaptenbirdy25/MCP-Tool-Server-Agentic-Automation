from __future__ import annotations

from agent import ToolClient, run_simple_ops_flow

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "dev-key"


def scenario_1():
    print("\n--- Scenario 1: första körning ---")
    client = ToolClient(BASE_URL, API_KEY)
    run_simple_ops_flow(client, customer_name="ACME", idem_key="demo-acme-ticket-001")


def scenario_2():
    print("\n--- Scenario 2: samma igen (idempotency ska undvika dubblett) ---")
    client = ToolClient(BASE_URL, API_KEY)
    run_simple_ops_flow(client, customer_name="ACME", idem_key="demo-acme-ticket-001")


if __name__ == "__main__":
    scenario_1()
    scenario_2()
