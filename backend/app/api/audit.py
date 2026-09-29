from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.db.session import get_db
from app.deps import get_current_user
from app.services.audit import verify_audit_chain

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit(
    subject_type: str | None = None,
    subject_id: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = db.query(AuditLog)
    if subject_type:
        q = q.filter(AuditLog.subject_type == subject_type)
    if subject_id:
        q = q.filter(AuditLog.subject_id == subject_id)
    entries = q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id": e.id,
            "ts": e.ts.isoformat() if e.ts else None,
            "actor_id": e.actor_id,
            "action": e.action,
            "subject_type": e.subject_type,
            "subject_id": e.subject_id,
            "hash": e.hash,
        }
        for e in entries
    ]


@router.get("/verify")
def verify_chain(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return verify_audit_chain(db)
