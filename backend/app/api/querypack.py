from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.extended_models import DataConflict
from app.db.models import Mine, User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.audit import append_audit
from app.services.query_pack import build_bundle, export_bundle_pdf

router = APIRouter(tags=["query-pack"])


@router.get("/reports/query-pack")
def get_query_pack(
    mine_id: int,
    period_start: date,
    period_end: date,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.query(Mine).filter(Mine.id == mine_id).first():
        raise HTTPException(404, "Mine not found")
    return build_bundle(db, mine_id, period_start, period_end)


@router.get("/reports/query-pack.pdf")
def download_query_pack(
    mine_id: int,
    period_start: date,
    period_end: date,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bundle = build_bundle(db, mine_id, period_start, period_end)
    path = export_bundle_pdf(bundle)
    append_audit(db, user.id, "EXPORT", "QUERY_PACK", mine_id,
                 {"period": f"{period_start}..{period_end}"})
    db.commit()
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/conflicts")
def list_conflicts(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(DataConflict)
    if status_filter:
        q = q.filter(DataConflict.status == status_filter)
    return [
        {
            "id": c.id,
            "subject_type": c.subject_type,
            "subject_key": c.subject_key,
            "system_value": c.system_value,
            "external_value": c.external_value,
            "external_source": c.external_source,
            "status": c.status,
            "resolution_note": c.resolution_note,
            "created_at": c.created_at.isoformat(),
        }
        for c in q.order_by(DataConflict.created_at.desc()).limit(200).all()
    ]


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: int,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conflict = db.query(DataConflict).filter(DataConflict.id == conflict_id).first()
    if not conflict:
        raise HTTPException(404, "Conflict not found")
    resolution = body.get("resolution", "")
    if resolution not in ("RESOLVED_SYSTEM", "RESOLVED_EXTERNAL"):
        raise HTTPException(422, "resolution must be RESOLVED_SYSTEM or RESOLVED_EXTERNAL")
    note = (body.get("note") or "").strip()
    if not note:
        raise HTTPException(422, "A human resolution note is required")

    conflict.status = resolution
    conflict.resolution_note = note
    conflict.resolved_by = user.id
    append_audit(db, user.id, "RESOLVE_CONFLICT", "DATA_CONFLICT", conflict.id,
                 {"resolution": resolution, "note": note})
    db.commit()
    return {"ok": True, "id": conflict.id, "status": conflict.status}
