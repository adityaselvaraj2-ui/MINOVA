"""Rain-impact statistics + plan-change engine (all deterministic Python).

- Rain-impact model: per mine+month-group, baseline = median dry-day output
  (rain < 1mm); productivity ratio per rainfall bin with next-day lag,
  reported as P25/P50/P75 with sample size n. If n < plan_min_sample_n,
  returns "insufficient evidence" - never a number.
- Capacity cap = P95 of historical daily output.
- Plan engine: expected loss vs plan for forecast rain, proposed
  redistribution to neighbouring dry days within the cap; remaining
  shortfall shown. Never auto-applied - persisted as plan_suggestion.
"""
from __future__ import annotations

import calendar
import statistics
from datetime import date

from sqlalchemy.orm import Session

from app.config import settings
from app.db.extended_models import WeatherDaily
from app.db.models import ShiftEntry, Target

BINS = ["0-1", "1-5", "5-20", "20-50", "50+"]


def _bin(rain_mm: float) -> str:
    if rain_mm < 1:
        return "0-1"
    if rain_mm < 5:
        return "1-5"
    if rain_mm < 20:
        return "5-20"
    if rain_mm < 50:
        return "20-50"
    return "50+"


def _daily_output(db: Session, mine_id: int) -> dict[date, int]:
    """Mine-level daily production (t) from APPROVED shift entries."""
    rows = (
        db.query(ShiftEntry.work_date,
                 (ShiftEntry.production_milli_t / 1000).label("t"))
        .filter(ShiftEntry.mine_id == mine_id, ShiftEntry.status == "APPROVED")
        .all()
    )
    out: dict[date, float] = {}
    for r in rows:
        out[r[0]] = out.get(r[0], 0) + float(r[1])
    return {d: int(round(v)) for d, v in out.items()}


def rain_impact_table(db: Session, mine_id: int) -> dict:
    """Baseline + per-bin ratios with lag, or insufficient-evidence."""
    rain = {
        r.date: (r.rain_mm_x10 / 10.0)
        for r in db.query(WeatherDaily)
        .filter(WeatherDaily.mine_id == mine_id, WeatherDaily.is_forecast.is_(False))
        .all()
    }
    output = _daily_output(db, mine_id)
    common = sorted(set(rain) & set(output))
    if len(common) < settings.plan_min_sample_n:
        return {"sufficient": False, "n": len(common), "message": "insufficient evidence"}

    by_monthgroup: dict[str, dict[str, list[int]]] = {}
    for d in common:
        g = "monsoon" if d.month in (6, 7, 8, 9, 10, 11) else "dry"
        b = _bin(rain[d])
        by_monthgroup.setdefault(g, {}).setdefault(b, []).append(output[d])
        # next-day lag: day after 20mm+ rain
        if rain[d] >= 20:
            nd = date.fromordinal(d.toordinal() + 1)
            if nd in output:
                by_monthgroup[g].setdefault("lag-next-day", []).append(output[nd])

    dry_vals = by_monthgroup.get("dry", {}).get("0-1", [])
    if not dry_vals:
        dry_vals = [output[d] for d in common if rain[d] < 1]
    baseline = statistics.median(dry_vals) if dry_vals else 0
    if baseline <= 0:
        return {"sufficient": False, "n": len(common), "message": "insufficient evidence"}

    table = {"sufficient": True, "n": len(common), "baseline_dry_t": baseline, "bins": {}}
    for g, bins in by_monthgroup.items():
        table["bins"][g] = {}
        for b, vals in bins.items():
            if not vals:
                continue
            ratios = [v / baseline for v in vals]
            table["bins"][g][b] = {
                "n": len(vals),
                "p25": (
                    round(statistics.quantiles(ratios, n=4)[0], 3)
                    if len(vals) >= 4 else round(min(ratios), 3)
                ),
                "p50": round(statistics.median(ratios), 3),
                "p75": (
                    round(statistics.quantiles(ratios, n=4)[2], 3)
                    if len(vals) >= 4 else round(max(ratios), 3)
                ),
            }
    return table


def capacity_cap(db: Session, mine_id: int) -> int:
    vals = sorted(_daily_output(db, mine_id).values())
    if not vals:
        return 0
    k = max(0, int(round(settings.plan_capacity_pct / 100 * (len(vals) - 1))))
    return vals[k]


def monthly_target_t(db: Session, mine_id: int, year: int, month: int) -> int | None:
    import calendar
    from datetime import date as _d
    t = (
        db.query(Target)
        .filter(
            Target.mine_id == mine_id,
            Target.period_level == "MONTHLY",
            Target.metric_code == "production_milli_t",
            Target.period_start == _d(year, month, 1),
            Target.period_end == _d(year, month, calendar.monthrange(year, month)[1]),
        )
        .first()
    )
    return (t.value_int // 1000) if t else None


def build_plan_suggestion(
    db: Session, mine_id: int, days: int | None = None,
) -> dict:
    """Deterministic plan-change suggestion for the next N days."""
    days = days or settings.plan_horizon_days
    today = date.today()

    forecast = (
        db.query(WeatherDaily)
        .filter(
            WeatherDaily.mine_id == mine_id,
            WeatherDaily.is_forecast.is_(True),
            WeatherDaily.date >= today,
            WeatherDaily.date <= date.fromordinal(today.toordinal() + days - 1),
        )
        .order_by(WeatherDaily.date)
        .all()
    )
    if not forecast:
        return {"ok": False, "reason": "No forecast rows - operator must import forecast CSV"}

    impact = rain_impact_table(db, mine_id)
    if not impact.get("sufficient"):
        return {"ok": False, "reason": impact.get("message", "insufficient evidence"),
                "n": impact.get("n")}

    cap = capacity_cap(db, mine_id)
    baseline = impact["baseline_dry_t"]
    # Physical reality: the catch-up cap can never sit below what a normal
    # dry day already delivers; clamp to the baseline when data is sparse.
    cap = max(cap, int(baseline)) if cap else cap
    group = "monsoon" if today.month in (6, 7, 8, 9, 10, 11) else "dry"
    bins = impact["bins"].get(group, impact["bins"].get("dry", {}))

    target = monthly_target_t(db, mine_id, today.year, today.month)
    achieved = sum(
        v for d, v in _daily_output(db, mine_id).items()
        if d.year == today.year and d.month == today.month
    )
    month_end = date(
        today.year, today.month,
        calendar.monthrange(today.year, today.month)[1],
    )
    remaining_days = max(1, (month_end - today).days)

    plan_rows = []
    total_loss = 0
    for r in forecast:
        rain = r.rain_mm_x10 / 10.0
        b = _bin(rain)
        ratio = bins.get(b, {}).get("p50", 1.0) if b != "0-1" else 1.0
        lag_ratio = bins.get("lag-next-day", {}).get("p50", 1.0)
        if b == "0-1" and any(
            rr.rain_mm_x10 / 10.0 >= 20 and 0 < (r.date - rr.date).days <= 1
            for rr in forecast
        ):
            ratio = min(ratio, lag_ratio)
        expected = int(round(baseline * ratio))
        plan_t = int(round(target / max(1, remaining_days))) if target else cap // 2
        loss = max(0, plan_t - expected)
        total_loss += loss
        plan_rows.append({
            "date": r.date.isoformat(),
            "rain_mm": rain,
            "bin": b,
            "ratio_p50": ratio,
            "expected_output_t": expected,
            "plan_t": plan_t,
            "expected_loss_t": loss,
        })

    # Redistribution: move recoverable loss to dry days with headroom
    recoverable = 0
    for row in plan_rows:
        if row["expected_loss_t"] > 0:
            continue
        headroom = max(0, cap - row["expected_output_t"])
        pending_loss = sum(
            x["expected_loss_t"] for x in plan_rows if x["expected_loss_t"] > 0
        )
        extra = min(headroom, pending_loss - recoverable)
        if extra > 0:
            row["proposed_extra_t"] = extra
            recoverable += extra
    unrecoverable = max(0, total_loss - recoverable)

    return {
        "ok": True,
        "mine_id": mine_id,
        "horizon_days": days,
        "baseline_dry_t": baseline,
        "capacity_cap_t": cap,
        "monthly_target_t": target,
        "achieved_to_date_t": achieved,
        "remaining_days": remaining_days,
        "rows": plan_rows,
        "total_expected_loss_t": total_loss,
        "recoverable_t": recoverable,
        "unrecoverable_shortfall_t": unrecoverable,
        "evidence": {
            "impact_table": impact,
            "forecast_rows": len(forecast),
        },
    }
