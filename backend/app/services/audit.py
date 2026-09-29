from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def _compute_hash(prev_hash: str | None, record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, default=str)
    data = (prev_hash or "") + payload
    return hashlib.sha256(data.encode()).hexdigest()


def append_audit(
    db: Session,
    actor_id: int | None,
    action: str,
    subject_type: str,
    subject_id: int,
    payload: dict | None = None,
) -> AuditLog:
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = last.hash if last else None

    record = {
        "action": action,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "actor_id": actor_id,
        **(payload or {}),
    }
    h = _compute_hash(prev_hash, record)

    entry = AuditLog(
        ts=datetime.now(timezone.utc),
        actor_id=actor_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        payload_json=json.dumps(record, default=str),
        prev_hash=prev_hash,
        hash=h,
    )
    db.add(entry)
    return entry


def verify_audit_chain(db: Session) -> dict:
    entries = db.query(AuditLog).order_by(AuditLog.id).all()
    if not entries:
        return {"valid": True, "count": 0}

    prev_hash = None
    for i, entry in enumerate(entries):
        record = json.loads(entry.payload_json) if entry.payload_json else {}
        expected = _compute_hash(prev_hash, record)
        if entry.hash != expected:
            return {
                "valid": False,
                "count": len(entries),
                "first_break_at": i,
                "entry_id": entry.id,
                "expected_hash": expected,
                "actual_hash": entry.hash,
            }
        if entry.prev_hash != prev_hash:
            return {
                "valid": False,
                "count": len(entries),
                "first_break_at": i,
                "entry_id": entry.id,
                "detail": "prev_hash mismatch",
            }
        prev_hash = entry.hash

    return {"valid": True, "count": len(entries)}
