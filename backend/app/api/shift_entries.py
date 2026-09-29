from __future__ import annotations

import hashlib
import json
import uuid as uuid_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models import DowntimeEvent, ShiftEntry, User
from app.db.session import get_db
from app.deps import get_current_user
from app.schemas.shift_entries import (
    ActionComment,
    ShiftEntryCreate,
    ShiftEntryOut,
    ShiftEntryUpdate,
)
from app.services.approvals import approve_entry, return_entry, submit_entry
from app.services.audit import append_audit
from app.services.validation import validate_shift_entry

router = APIRouter(prefix="/shift-entries", tags=["shift-entries"])


def _compute_content_hash(entry_data: dict) -> str:
    payload = json.dumps(entry_data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _build_entry_out(entry: ShiftEntry, warnings: list[str] | None = None) -> dict:
    data = {
        "id": entry.id,
        "uuid": entry.uuid,
        "mine_id": entry.mine_id,
        "bench_id": entry.bench_id,
        "work_date": entry.work_date,
        "shift_code": entry.shift_code,
        "foreman_id": entry.foreman_id,
        "planned_min": entry.planned_min,
        "workers_present": entry.workers_present,
        "production_milli_t": entry.production_milli_t,
        "ob_milli_m3": entry.ob_milli_m3,
        "stoppage_min": entry.stoppage_min,
        "operating_min": entry.operating_min,
        "weather_code": entry.weather_code,
        "rainfall_mm_x10": entry.rainfall_mm_x10,
        "temperature_c_x10": entry.temperature_c_x10,
        "remarks": entry.remarks,
        "status": entry.status,
        "version": entry.version,
        "supersedes_id": entry.supersedes_id,
        "current_step": entry.current_step,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "downtime_events": [
            {
                "id": de.id,
                "equipment_id": de.equipment_id,
                "category": de.category,
                "start_min": de.start_min,
                "end_min": de.end_min,
                "duration_min": de.duration_min,
                "cause_text": de.cause_text,
                "evidence_path": de.evidence_path,
            }
            for de in entry.downtime_events
        ],
        "warnings": warnings or [],
    }
    return data


@router.post("", response_model=ShiftEntryOut, status_code=status.HTTP_201_CREATED)
def create_shift_entry(
    body: ShiftEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.role.can_enter:
        raise HTTPException(403, "User role cannot create shift entries")

    dt_dicts = [d.model_dump() for d in body.downtime_events]
    result = validate_shift_entry(
        db,
        mine_id=body.mine_id,
        bench_id=body.bench_id,
        work_date=body.work_date,
        shift_code=body.shift_code,
        foreman_id=user.id,
        planned_min=body.planned_min,
        workers_present=body.workers_present,
        production_milli_t=body.production_milli_t,
        ob_milli_m3=body.ob_milli_m3,
        downtime_events=dt_dicts,
    )
    if not result.valid:
        raise HTTPException(422, detail={"errors": result.errors})

    total_stoppage = sum(d.end_min - d.start_min for d in body.downtime_events)
    operating_min = body.planned_min - total_stoppage

    entry = ShiftEntry(
        uuid=str(uuid_mod.uuid4()),
        mine_id=body.mine_id,
        bench_id=body.bench_id,
        work_date=body.work_date,
        shift_code=body.shift_code,
        foreman_id=user.id,
        planned_min=body.planned_min,
        workers_present=body.workers_present,
        production_milli_t=body.production_milli_t,
        ob_milli_m3=body.ob_milli_m3,
        stoppage_min=total_stoppage,
        operating_min=operating_min,
        weather_code=body.weather_code,
        rainfall_mm_x10=body.rainfall_mm_x10,
        temperature_c_x10=body.temperature_c_x10,
        remarks=body.remarks,
        status="DRAFT",
        version=1,
        current_step=0,
    )
    entry.content_hash = _compute_content_hash(body.model_dump(mode="json"))
    db.add(entry)
    db.flush()

    for de_in in body.downtime_events:
        dur = de_in.end_min - de_in.start_min
        db.add(DowntimeEvent(
            shift_entry_id=entry.id,
            equipment_id=de_in.equipment_id,
            category=de_in.category,
            start_min=de_in.start_min,
            end_min=de_in.end_min,
            duration_min=dur,
            cause_text=de_in.cause_text,
            evidence_path=de_in.evidence_path,
        ))

    append_audit(db, user.id, "CREATE", "SHIFT_ENTRY", entry.id)
    db.commit()
    db.refresh(entry)
    return _build_entry_out(entry, result.warnings)


@router.put("/{entry_id}", response_model=ShiftEntryOut)
def update_shift_entry(
    entry_id: int,
    body: ShiftEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(ShiftEntry).filter(ShiftEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Shift entry not found")
    if entry.status not in ("DRAFT", "RETURNED"):
        raise HTTPException(400, f"Cannot edit entry in status {entry.status}")
    if entry.foreman_id != user.id:
        raise HTTPException(403, "Only the entry's foreman can edit it")

    updates = body.model_dump(exclude_unset=True)
    for field_name in (
        "planned_min", "workers_present", "production_milli_t", "ob_milli_m3",
        "weather_code", "rainfall_mm_x10", "temperature_c_x10", "remarks",
    ):
        if field_name in updates:
            setattr(entry, field_name, updates[field_name])

    if body.downtime_events is not None:
        db.query(DowntimeEvent).filter(DowntimeEvent.shift_entry_id == entry.id).delete()
        total_stop = 0
        for de_in in body.downtime_events:
            dur = de_in.end_min - de_in.start_min
            total_stop += dur
            db.add(DowntimeEvent(
                shift_entry_id=entry.id,
                equipment_id=de_in.equipment_id,
                category=de_in.category,
                start_min=de_in.start_min,
                end_min=de_in.end_min,
                duration_min=dur,
                cause_text=de_in.cause_text,
                evidence_path=de_in.evidence_path,
            ))
        entry.stoppage_min = total_stop
        entry.operating_min = entry.planned_min - total_stop
    else:
        total_stop = sum(de.duration_min for de in entry.downtime_events)
        entry.stoppage_min = total_stop
        entry.operating_min = entry.planned_min - total_stop

    entry.updated_at = datetime.now(timezone.utc)
    append_audit(db, user.id, "UPDATE", "SHIFT_ENTRY", entry.id)
    db.commit()
    db.refresh(entry)
    return _build_entry_out(entry)


@router.get("", response_model=list[ShiftEntryOut])
def list_shift_entries(
    mine_id: int | None = None,
    bench_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    work_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ShiftEntry).filter(ShiftEntry.status != "SUPERSEDED")
    if mine_id:
        q = q.filter(ShiftEntry.mine_id == mine_id)
    elif user.mine_id:
        q = q.filter(ShiftEntry.mine_id == user.mine_id)
    if bench_id:
        q = q.filter(ShiftEntry.bench_id == bench_id)
    if status_filter:
        q = q.filter(ShiftEntry.status == status_filter)
    if work_date:
        q = q.filter(ShiftEntry.work_date == work_date)

    entries = (
        q.order_by(ShiftEntry.work_date.desc(), ShiftEntry.shift_code)
        .offset(offset).limit(limit).all()
    )
    return [_build_entry_out(e) for e in entries]


@router.post("/{entry_id}/submit", response_model=ShiftEntryOut)
def submit(entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entry = db.query(ShiftEntry).filter(ShiftEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Shift entry not found")
    try:
        submit_entry(db, entry, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.commit()
    db.refresh(entry)
    return _build_entry_out(entry)


@router.post("/{entry_id}/approve", response_model=ShiftEntryOut)
def approve(entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entry = db.query(ShiftEntry).filter(ShiftEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Shift entry not found")
    try:
        approve_entry(db, entry, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.commit()
    db.refresh(entry)
    return _build_entry_out(entry)


@router.post("/{entry_id}/return", response_model=ShiftEntryOut)
def return_entry_endpoint(
    entry_id: int,
    body: ActionComment,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(ShiftEntry).filter(ShiftEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Shift entry not found")
    try:
        return_entry(db, entry, user, body.comment)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.commit()
    db.refresh(entry)
    return _build_entry_out(entry)


@router.post("/{entry_id}/correct", response_model=ShiftEntryOut)
def correct_entry(
    entry_id: int,
    body: ShiftEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    old = db.query(ShiftEntry).filter(ShiftEntry.id == entry_id).first()
    if not old:
        raise HTTPException(404, "Shift entry not found")
    if old.status != "APPROVED":
        raise HTTPException(400, "Can only correct APPROVED entries")

    old.status = "SUPERSEDED"
    old.updated_at = datetime.now(timezone.utc)

    total_stoppage = sum(d.end_min - d.start_min for d in body.downtime_events)
    new_entry = ShiftEntry(
        uuid=str(uuid_mod.uuid4()),
        mine_id=body.mine_id,
        bench_id=body.bench_id,
        work_date=body.work_date,
        shift_code=body.shift_code,
        foreman_id=user.id,
        planned_min=body.planned_min,
        workers_present=body.workers_present,
        production_milli_t=body.production_milli_t,
        ob_milli_m3=body.ob_milli_m3,
        stoppage_min=total_stoppage,
        operating_min=body.planned_min - total_stoppage,
        weather_code=body.weather_code,
        rainfall_mm_x10=body.rainfall_mm_x10,
        temperature_c_x10=body.temperature_c_x10,
        remarks=body.remarks,
        status="DRAFT",
        version=old.version + 1,
        supersedes_id=old.id,
        current_step=0,
    )
    db.add(new_entry)
    db.flush()

    for de_in in body.downtime_events:
        dur = de_in.end_min - de_in.start_min
        db.add(DowntimeEvent(
            shift_entry_id=new_entry.id,
            equipment_id=de_in.equipment_id,
            category=de_in.category,
            start_min=de_in.start_min,
            end_min=de_in.end_min,
            duration_min=dur,
            cause_text=de_in.cause_text,
            evidence_path=de_in.evidence_path,
        ))

    append_audit(db, user.id, "CORRECT", "SHIFT_ENTRY", new_entry.id, {
        "supersedes": old.id,
    })
    db.commit()
    db.refresh(new_entry)
    return _build_entry_out(new_entry)
