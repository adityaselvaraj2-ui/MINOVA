from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import ShiftEntry, User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.approvals import can_user_approve_entry

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/queue")
def get_approval_queue(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.role.can_approve:
        return []

    q = db.query(ShiftEntry).filter(ShiftEntry.status == "SUBMITTED")
    if user.mine_id:
        q = q.filter(ShiftEntry.mine_id == user.mine_id)

    submitted = q.order_by(ShiftEntry.work_date.desc()).limit(200).all()
    queue = []
    for entry in submitted:
        if can_user_approve_entry(db, user, entry):
            queue.append({
                "id": entry.id,
                "uuid": entry.uuid,
                "mine_id": entry.mine_id,
                "bench_id": entry.bench_id,
                "work_date": entry.work_date.isoformat(),
                "shift_code": entry.shift_code,
                "production_milli_t": entry.production_milli_t,
                "ob_milli_m3": entry.ob_milli_m3,
                "status": entry.status,
                "current_step": entry.current_step,
                "version": entry.version,
            })
    return queue
