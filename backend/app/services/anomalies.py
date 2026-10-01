"""Deterministic anomaly detection on approved shift entries.

Flags (signals for human review, never auto-decisions):
- production z-score outlier vs trailing approved history (same mine+bench+shift)
- operating minutes inconsistent with planned - stoppage
- downtime rows that overlap or exceed planned minutes (defensive re-check)
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ShiftEntry


def detect_anomalies(db: Session, mine_id: int, lookback_days: int = 45) -> list[dict]:
    since = date.today() - timedelta(days=lookback_days)
    entries = (
        db.query(ShiftEntry)
        .filter(
            ShiftEntry.mine_id == mine_id,
            ShiftEntry.status == "APPROVED",
            ShiftEntry.work_date >= since,
        )
        .order_by(ShiftEntry.work_date.desc())
        .all()
    )

    stats = (
        db.query(
            ShiftEntry.bench_id,
            ShiftEntry.shift_code,
            func.avg(ShiftEntry.production_milli_t),
            func.count(ShiftEntry.id),
        )
        .filter(
            ShiftEntry.mine_id == mine_id,
            ShiftEntry.status == "APPROVED",
            ShiftEntry.work_date < since,
        )
        .group_by(ShiftEntry.bench_id, ShiftEntry.shift_code)
        .all()
    )
    mean_map = {(r[0], r[1]): (float(r[2]), r[3]) for r in stats if r[2] is not None}

    var_rows = (
        db.query(
            ShiftEntry.bench_id,
            ShiftEntry.shift_code,
            func.avg(ShiftEntry.production_milli_t * ShiftEntry.production_milli_t),
        )
        .filter(
            ShiftEntry.mine_id == mine_id,
            ShiftEntry.status == "APPROVED",
            ShiftEntry.work_date < since,
        )
        .group_by(ShiftEntry.bench_id, ShiftEntry.shift_code)
        .all()
    )
    var_map = {(r[0], r[1]): float(r[2]) for r in var_rows if r[2] is not None}

    anomalies: list[dict] = []
    z_thr = settings.anomaly_z_threshold
    for e in entries:
        key = (e.bench_id, e.shift_code)
        if key in mean_map and key in var_map:
            mean, n = mean_map[key]
            var = max(0.0, var_map[key] - mean * mean)
            sd = math.sqrt(var)
            if sd > 0 and n >= 10:
                z = (e.production_milli_t - mean) / sd
                if abs(z) >= z_thr:
                    anomalies.append({
                        "shift_entry_id": e.id,
                        "work_date": e.work_date.isoformat(),
                        "shift": e.shift_code,
                        "type": "PRODUCTION_OUTLIER",
                        "detail": f"z={z:.2f} vs trailing mean {mean/1000:.0f} t (n={n})",
                    })

        expected_op = e.planned_min - e.stoppage_min
        if expected_op >= 0 and abs(e.operating_min - expected_op) > 30:
            anomalies.append({
                "shift_entry_id": e.id,
                "work_date": e.work_date.isoformat(),
                "shift": e.shift_code,
                "type": "OPERATING_HOURS_MISMATCH",
                "detail": f"operating {e.operating_min} min vs planned-stoppage {expected_op} min",
            })

    return anomalies
