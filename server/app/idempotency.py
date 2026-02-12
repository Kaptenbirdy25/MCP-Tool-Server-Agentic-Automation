from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from .models import IdempotencyRecord


def get_cached_response(db: Session, tool: str, key: str) -> dict[str, Any] | None:
    rec = db.query(IdempotencyRecord).filter_by(tool=tool, key=key).first()
    if not rec:
        return None
    return IdempotencyRecord.loads(rec.response_json)


def store_response(db: Session, tool: str, key: str, response: dict[str, Any]) -> None:
    rec = IdempotencyRecord(tool=tool, key=key, response_json=IdempotencyRecord.dumps(response))
    db.add(rec)
    db.commit()
