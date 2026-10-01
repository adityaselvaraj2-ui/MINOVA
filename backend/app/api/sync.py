"""Offline-first capture endpoint (secure sync).

The field client (Tauri desktop runs the same UI offline; a future Flutter
client uses the same contract) queues shift entries locally while offline
and replays them here when connectivity returns:

    POST /shift-entries/sync
    {
      "device_id": "tab-op-01",
      "captured_at": "2026-09-30T05:10:00Z",
      "entries": [ { ...ShiftEntryCreate... }, ... ]
    }

Server behavior per abstract: "When the device reconnects, the server
validates the submitted information before accepting it into the central
system." -> each entry goes through the SAME validation + duplicate rules
as online entry; per-entry result (accepted/rejected with reasons) is
returned so the client can keep rejects locally. Everything is
audit-logged with the device id.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.schemas.shift_entries import ShiftEntryCreate
from app.services.audit import append_audit

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/shift-entries")
def sync_shift_entries(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.api.shift_entries import create_shift_entry

    entries = body.get("entries") or []
    device_id = str(body.get("device_id") or "unknown")
    captured_at = body.get("captured_at")

    results = []
    for i, raw in enumerate(entries):
        try:
            payload = ShiftEntryCreate(**raw)
            entry = create_shift_entry(payload, db=db, user=user)
            results.append({"index": i, "ok": True, "id": entry.id,
                            "uuid": entry.uuid, "status": entry.status})
        except Exception as exc:  # noqa: BLE001 - per-entry isolation
            db.rollback()
            results.append({"index": i, "ok": False, "error": str(exc)[:300]})

    append_audit(db, user.id, "SYNC_PULL", "SHIFT_ENTRY", 0, {
        "device_id": device_id,
        "captured_at": captured_at,
        "count": len(entries),
        "accepted": sum(1 for r in results if r["ok"]),
        "rejected": sum(1 for r in results if not r["ok"]),
    })
    db.commit()
    return {
        "device_id": device_id,
        "received": len(entries),
        "accepted": sum(1 for r in results if r["ok"]),
        "rejected": sum(1 for r in results if not r["ok"]),
        "results": results,
    }


@router.get("/queue")
def sync_queue_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Recent sync operations for the UI status widget."""
    from app.db.models import AuditLog

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action == "SYNC_PULL")
        .order_by(AuditLog.id.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "ts": r.ts.isoformat() if r.ts else None,
            "actor_id": r.actor_id,
            "payload": r.payload_json,
        }
        for r in rows
    ]
