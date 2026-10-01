"""Daily-operations analytics over shift downtime events.

Ported from teammate architecture:
- stoppage_pareto: downtime hours by cause category, ranked, with cumulative %
- machine_utilization: per-machine downtime + availability vs planned window
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import DowntimeEvent, Equipment, ShiftEntry

CATEGORY_ALIASES = {
    "EQUIPMENT_FAILURE": "equipment_failure",
    "SCHEDULED_MAINTENANCE": "maintenance",
    "WEATHER": "weather",
    "FIRE_INCIDENT": "fire",
    "LABOUR": "labour",
    "SUPPLY": "supply",
    "OTHER": "other",
}


def stoppage_pareto(
    db: Session, date_from=None, date_to=None,
) -> dict:
    q = (
        db.query(DowntimeEvent)
        .join(ShiftEntry, DowntimeEvent.shift_entry_id == ShiftEntry.id)
    )
    if date_from is not None:
        q = q.filter(ShiftEntry.work_date >= date_from)
    if date_to is not None:
        q = q.filter(ShiftEntry.work_date <= date_to)

    by_cat: dict[str, float] = defaultdict(float)
    total = 0.0
    for ev in q.all():
        cat = CATEGORY_ALIASES.get(ev.category, "other")
        by_cat[cat] += ev.duration_min / 60.0
        total += ev.duration_min / 60.0

    ranked = sorted(by_cat.items(), key=lambda x: -x[1])
    out = []
    cum = 0.0
    for cat, hours in ranked:
        cum += hours
        out.append({
            "category": cat,
            "hours": round(hours, 2),
            "share_pct": round(100 * hours / total, 1) if total else 0.0,
            "cumulative_pct": round(100 * cum / total, 1) if total else 0.0,
        })
    return {"total_hours": round(total, 2), "categories": out}


def machine_utilization(
    db: Session, shift_minutes: int = 480,
) -> dict:
    """Availability per machine: share of shift-time with no downtime event.

    Planned window = number of shifts in which the machine appears in any
    downtime OR was available x shift length. We approximate planned window
    as shifts observed on benches where the equipment is deployed; simpler
    and robust: window = total shifts x shift_minutes per machine that has
    at least one downtime record, plus a fleet row for machines with none.
    """
    total_shifts = db.query(ShiftEntry).count()

    downtime = (
        db.query(
            Equipment.id,
            Equipment.code,
            Equipment.name,
            func.coalesce(func.sum(DowntimeEvent.duration_min), 0),
        )
        .outerjoin(DowntimeEvent, DowntimeEvent.equipment_id == Equipment.id)
        .group_by(Equipment.id)
        .all()
    )

    machines = []
    for _eq_id, code, name, down_min in downtime:
        down = float(down_min or 0)
        # window: assume the machine is rostered on every shift captured
        planned_min = total_shifts * shift_minutes
        availability = 100 * (planned_min - down) / planned_min if planned_min else 0.0
        machines.append({
            "machine": code,
            "name": name,
            "downtime_h": round(down / 60.0, 2),
            "availability_pct": round(availability, 2),
        })
    machines.sort(key=lambda m: m["availability_pct"])
    return {"shift_length_min": shift_minutes, "machines": machines}
