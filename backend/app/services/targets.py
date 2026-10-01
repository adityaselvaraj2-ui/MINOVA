"""Deterministic target-vs-actual analytics (no AI in the numbers).

Achievement %, top downtime causes, and previous-period comparison -
all computed from APPROVED data; the LLM may only narrate these later.
"""
from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import DowntimeEvent, ShiftEntry, Target


def _actuals(db: Session, mine_id: int, start: date, end: date) -> dict:
    rows = (
        db.query(
            func.sum(ShiftEntry.production_milli_t),
            func.sum(ShiftEntry.ob_milli_m3),
            func.sum(ShiftEntry.stoppage_min),
            func.sum(ShiftEntry.operating_min),
            func.count(ShiftEntry.id),
        )
        .filter(
            ShiftEntry.mine_id == mine_id,
            ShiftEntry.status == "APPROVED",
            ShiftEntry.work_date >= start,
            ShiftEntry.work_date <= end,
        )
        .first()
    )
    return {
        "production_t": (rows[0] or 0) / 1000.0,
        "ob_m3": (rows[1] or 0) / 1000.0,
        "stoppage_min": rows[2] or 0,
        "operating_min": rows[3] or 0,
        "entries": rows[4] or 0,
    }


def _target(db: Session, mine_id: int, start: date, end: date) -> float | None:
    """Most specific target whose period fully covers [start, end]."""
    t = (
        db.query(Target)
        .filter(
            Target.mine_id == mine_id,
            Target.metric_code == "production_milli_t",
            Target.period_start <= start,
            Target.period_end >= end,
        )
        .order_by(Target.period_start.desc())
        .first()
    )
    return (t.value_int / 1000.0) if t else None


def top_downtime_causes(
    db: Session, mine_id: int, start: date, end: date, top: int = 3,
) -> list[dict]:
    rows = (
        db.query(
            DowntimeEvent.category,
            func.sum(DowntimeEvent.duration_min),
        )
        .join(ShiftEntry, DowntimeEvent.shift_entry_id == ShiftEntry.id)
        .filter(
            ShiftEntry.mine_id == mine_id,
            ShiftEntry.status == "APPROVED",
            ShiftEntry.work_date >= start,
            ShiftEntry.work_date <= end,
        )
        .group_by(DowntimeEvent.category)
        .order_by(func.sum(DowntimeEvent.duration_min).desc())
        .limit(top)
        .all()
    )
    total = sum(r[1] for r in rows) or 1
    return [
        {"category": r[0], "minutes": r[1], "pct_of_top": round(100 * r[1] / total, 1)}
        for r in rows
    ]


def _prev_period(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    pe = date.fromordinal(start.toordinal() - 1)
    ps = date.fromordinal(pe.toordinal() - days + 1)
    return ps, pe


def month_boundaries_of(d: date) -> tuple[date, date]:
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def target_vs_actual(
    db: Session, mine_id: int, start: date, end: date,
) -> dict:
    actual = _actuals(db, mine_id, start, end)
    target = _target(db, mine_id, start, end)
    achievement = (
        round(100 * actual["production_t"] / target, 2)
        if target else None
    )

    ps, pe = _prev_period(start, end)
    prev = _actuals(db, mine_id, ps, pe)
    delta_pct = (
        round(100 * (actual["production_t"] - prev["production_t"]) / prev["production_t"], 2)
        if prev["production_t"] else None
    )

    facts = {
        "mine_id": mine_id,
        "period": f"{start} to {end}",
        "target_t": target,
        "actual_t": round(actual["production_t"], 3),
        "achievement_pct": achievement,
        "overburden_m3": round(actual["ob_m3"], 3),
        "stoppage_min": actual["stoppage_min"],
        "operating_min": actual["operating_min"],
        "entries": actual["entries"],
        "prev_period": f"{ps} to {pe}",
        "prev_actual_t": round(prev["production_t"], 3),
        "delta_vs_prev_pct": delta_pct,
        "top_downtime_causes": top_downtime_causes(db, mine_id, start, end),
    }
    facts["factual_summary"] = deterministic_summary(facts)
    return facts


def deterministic_summary(f: dict) -> str:
    """Plain factual sentence built ONLY from computed figures."""
    parts = []
    if f["target_t"]:
        parts.append(
            f"Production was {f['actual_t']:,.0f} t against a target of "
            f"{f['target_t']:,.0f} t ({f['achievement_pct']}% achievement)."
        )
    else:
        parts.append(f"Production was {f['actual_t']:,.0f} t (no target recorded).")
    if f["delta_vs_prev_pct"] is not None:
        word = "up" if f["delta_vs_prev_pct"] >= 0 else "down"
        parts.append(
            f"This is {word} {abs(f['delta_vs_prev_pct'])}% versus the previous "
            f"period ({f['prev_actual_t']:,.0f} t)."
        )
    if f["top_downtime_causes"]:
        top = f["top_downtime_causes"][0]
        parts.append(
            f"Largest recorded downtime cause: {top['category']} "
            f"({top['minutes']:,} min)."
        )
    return " ".join(parts)
