from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit.log"


def log_event(event: dict[str, Any]) -> None:
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        **event,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
