from __future__ import annotations

import os

DEFAULT_ALLOWED = {
    "search_customer",
    "create_ticket",
    "update_customer_status",
    "send_message",
    "get_incident_impact",
}


def allowed_tools() -> set[str]:
    raw = os.getenv("ALLOWED_TOOLS", "")
    if not raw.strip():
        return set(DEFAULT_ALLOWED)
    return {x.strip() for x in raw.split(",") if x.strip()}


def assert_allowed(tool: str) -> None:
    if tool not in allowed_tools():
        raise PermissionError(f"Tool not allowed by policy: {tool}")
