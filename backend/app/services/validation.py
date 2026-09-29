from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Bench, Mine, ShiftEntry, User


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


CAUSE_REQUIRED_CATEGORIES = {"EQUIPMENT_FAILURE", "FIRE_INCIDENT", "LABOUR"}


def validate_shift_entry(
    db: Session,
    mine_id: int,
    bench_id: int,
    work_date,
    shift_code: str,
    foreman_id: int,
    planned_min: int,
    workers_present: int,
    production_milli_t: int,
    ob_milli_m3: int,
    downtime_events: list[dict] | None = None,
    exclude_entry_id: int | None = None,
) -> ValidationResult:
    result = ValidationResult()
    shift_length = settings.shift_length_minutes

    if planned_min < 0:
        result.errors.append("planned_min must be non-negative")
    if planned_min > shift_length:
        result.errors.append(f"planned_min ({planned_min}) exceeds shift length ({shift_length})")
    if workers_present < 0:
        result.errors.append("workers_present must be non-negative")
    if production_milli_t < 0:
        result.errors.append("production must be non-negative")
    if ob_milli_m3 < 0:
        result.errors.append("overburden must be non-negative")

    if shift_code not in settings.shift_codes:
        result.errors.append(f"Invalid shift_code: {shift_code}")

    mine = db.query(Mine).filter(Mine.id == mine_id).first()
    if mine is None:
        result.errors.append(f"Mine {mine_id} not found")
        return result

    bench = db.query(Bench).filter(Bench.id == bench_id).first()
    if bench is None:
        result.errors.append(f"Bench {bench_id} not found")
    elif bench.mine_id != mine_id:
        result.errors.append(f"Bench {bench_id} does not belong to mine {mine_id}")

    foreman = db.query(User).filter(User.id == foreman_id).first()
    if foreman is None:
        result.errors.append(f"Foreman user {foreman_id} not found")
    elif foreman.mine_id is not None and foreman.mine_id != mine_id:
        result.errors.append(f"Foreman is not assigned to mine {mine_id}")

    q = db.query(ShiftEntry).filter(
        ShiftEntry.mine_id == mine_id,
        ShiftEntry.bench_id == bench_id,
        ShiftEntry.work_date == work_date,
        ShiftEntry.shift_code == shift_code,
        ShiftEntry.status.notin_(["SUPERSEDED"]),
    )
    if exclude_entry_id:
        q = q.filter(ShiftEntry.id != exclude_entry_id)
    existing = q.first()
    if existing:
        result.errors.append(
            f"Duplicate: entry already exists for this mine/bench/date/shift (id={existing.id})"
        )

    total_stoppage = 0
    if downtime_events:
        for i, evt in enumerate(downtime_events):
            s, e = evt.get("start_min", 0), evt.get("end_min", 0)
            if s < 0 or e < 0:
                result.errors.append(f"Downtime event {i}: negative time values")
            if s >= e:
                result.errors.append(f"Downtime event {i}: start ({s}) must be < end ({e})")
            if e > planned_min:
                result.errors.append(
                    f"Downtime event {i}: end ({e}) exceeds planned_min ({planned_min})"
                )
            cat = evt.get("category", "")
            if cat in CAUSE_REQUIRED_CATEGORIES and not evt.get("cause_text"):
                result.errors.append(
                    f"Downtime event {i}: {cat} requires cause_text"
                )
            total_stoppage += e - s

        sorted_events = sorted(downtime_events, key=lambda x: x.get("start_min", 0))
        for j in range(1, len(sorted_events)):
            if sorted_events[j].get("start_min", 0) < sorted_events[j - 1].get("end_min", 0):
                result.errors.append(f"Downtime events {j-1} and {j} overlap")

    if total_stoppage > planned_min:
        result.errors.append(
            f"Total downtime ({total_stoppage}) exceeds planned_min ({planned_min})"
        )

    _check_plausibility(db, mine_id, bench_id, shift_code, production_milli_t, result)

    return result


def _check_plausibility(
    db: Session,
    mine_id: int,
    bench_id: int,
    shift_code: str,
    production_milli_t: int,
    result: ValidationResult,
) -> None:
    from sqlalchemy import func

    recent = (
        db.query(
            func.avg(ShiftEntry.production_milli_t).label("avg"),
            func.count().label("cnt"),
        )
        .filter(
            ShiftEntry.mine_id == mine_id,
            ShiftEntry.bench_id == bench_id,
            ShiftEntry.shift_code == shift_code,
            ShiftEntry.status == "APPROVED",
        )
        .first()
    )

    if recent and recent.cnt and recent.cnt >= 10 and recent.avg:
        import math

        stddev_q = (
            db.query(
                func.avg(
                    (ShiftEntry.production_milli_t - recent.avg)
                    * (ShiftEntry.production_milli_t - recent.avg)
                ).label("var")
            )
            .filter(
                ShiftEntry.mine_id == mine_id,
                ShiftEntry.bench_id == bench_id,
                ShiftEntry.shift_code == shift_code,
                ShiftEntry.status == "APPROVED",
            )
            .first()
        )
        if stddev_q and stddev_q.var and stddev_q.var > 0:
            stddev = math.sqrt(float(stddev_q.var))
            if abs(production_milli_t - float(recent.avg)) > 3 * stddev:
                result.warnings.append(
                    f"Production ({production_milli_t}) is >3 std devs from "
                    f"trailing mean ({recent.avg:.0f})"
                )
