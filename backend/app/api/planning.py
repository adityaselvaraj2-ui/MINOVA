from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.extended_models import PlanSuggestion, WeatherDaily
from app.db.models import Mine, User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.audit import append_audit
from app.services.plan import build_plan_suggestion, capacity_cap, rain_impact_table
from app.services.weather import (
    forecast_window,
    import_csv_for_all_mines,
)

router = APIRouter(prefix="/planning", tags=["planning"])


@router.post("/weather/import")
def import_weather(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Operator action: (re)import CSV weather files for all mines."""
    result = import_csv_for_all_mines(db)
    append_audit(db, user.id, "WEATHER_IMPORT", "WEATHER", 0, result)
    db.commit()
    return {"ok": True, "rows_by_mine": result}


@router.get("/weather/forecast")
def get_forecast(
    mine_id: int,
    days: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mine = db.query(Mine).filter(Mine.id == mine_id).first()
    if not mine:
        raise HTTPException(404, "Mine not found")
    rows, stale = forecast_window(db, mine, days or settings.plan_horizon_days)
    return {
        "mine_id": mine_id,
        "stale": stale,
        "rows": [
            {
                "date": r.date.isoformat(),
                "rain_mm": r.rain_mm_x10 / 10.0,
                "temp_max_c": (r.temp_max_x10 / 10.0) if r.temp_max_x10 is not None else None,
                "source": r.source,
            }
            for r in rows
        ],
    }


@router.get("/rain-impact")
def get_rain_impact(
    mine_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return rain_impact_table(db, mine_id)


@router.post("/suggest")
def suggest_plan(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mine_id = body.get("mine_id")
    if not mine_id:
        raise HTTPException(422, "mine_id required")
    result = build_plan_suggestion(db, mine_id, body.get("days"))
    if result.get("ok"):
        suggestion = PlanSuggestion(
            mine_id=mine_id,
            horizon_start=date.fromisoformat(result["rows"][0]["date"]),
            horizon_end=date.fromisoformat(result["rows"][-1]["date"]),
            payload_json=json.dumps(result["rows"], default=str),
            status="PENDING",
        )
        db.add(suggestion)
        db.flush()
        result["suggestion_id"] = suggestion.id
        append_audit(db, user.id, "PLAN_SUGGEST", "PLAN_SUGGESTION", suggestion.id,
                     {"horizon": f"{result['rows'][0]['date']}..{result['rows'][-1]['date']}"})
    db.commit()
    return result


@router.get("/suggestions")
def list_suggestions(
    mine_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(PlanSuggestion)
    if mine_id:
        q = q.filter(PlanSuggestion.mine_id == mine_id)
    return [
        {
            "id": s.id,
            "mine_id": s.mine_id,
            "horizon": f"{s.horizon_start}..{s.horizon_end}",
            "status": s.status,
            "reason": s.reason,
            "decided_by": s.decided_by,
            "created_at": s.created_at.isoformat(),
        }
        for s in q.order_by(PlanSuggestion.created_at.desc()).limit(50).all()
    ]


@router.post("/suggestions/{suggestion_id}/decide")
def decide_suggestion(
    suggestion_id: int,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    suggestion = db.query(PlanSuggestion).filter(PlanSuggestion.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(404, "Suggestion not found")
    decision = body.get("decision", "")
    if decision not in ("ACCEPTED", "REJECTED"):
        raise HTTPException(422, "decision must be ACCEPTED or REJECTED")
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(422, "A reason is required for accept/reject (audit)")

    suggestion.status = decision
    suggestion.reason = reason
    suggestion.decided_by = user.id
    append_audit(db, user.id, f"PLAN_{decision}", "PLAN_SUGGESTION", suggestion.id,
                 {"reason": reason})
    db.commit()
    return {"ok": True, "id": suggestion.id, "status": suggestion.status}


@router.get("/backtest")
def backtest(
    mine_id: int,
    start: date,
    end: date,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replay past rain as if it were the forecast: predicted vs actual loss.

    Uses the same deterministic impact table; compares predicted loss against
    shortfall implied by actual output vs plan (plan = dry-day baseline).
    """
    from app.services.plan import _bin, _daily_output, rain_impact_table

    impact = rain_impact_table(db, mine_id)
    if not impact.get("sufficient"):
        return {"ok": False, "reason": impact.get("message"), "n": impact.get("n")}

    baseline = impact["baseline_dry_t"]
    output = _daily_output(db, mine_id)
    group_bins = impact["bins"]

    rows = []
    abs_errs = []

    rain_rows = (
        db.query(WeatherDaily)
        .filter(
            WeatherDaily.mine_id == mine_id,
            WeatherDaily.date >= start,
            WeatherDaily.date <= end,
        )
        .all()
    )
    rain_map = {r.date: r.rain_mm_x10 / 10.0 for r in rain_rows}

    for d in sorted(set(output) & set(rain_map)):
        if not (start <= d <= end):
            continue
        rain = rain_map[d]
        g = "monsoon" if d.month in (6, 7, 8, 9, 10, 11) else "dry"
        bins = group_bins.get(g, group_bins.get("dry", {}))
        b = _bin(rain)
        ratio = bins.get(b, {}).get("p50", 1.0) if b != "0-1" else 1.0
        predicted = int(round(baseline * ratio))
        actual = output[d]
        plan_t = int(round(baseline))
        pred_loss = max(0, plan_t - predicted)
        actual_loss = max(0, plan_t - actual)
        abs_errs.append(abs(pred_loss - actual_loss))
        rows.append({
            "date": d.isoformat(),
            "rain_mm": rain,
            "predicted_loss_t": pred_loss,
            "actual_loss_t": actual_loss,
        })

    if not rows:
        return {"ok": False, "reason": "No overlapping output+weather rows in period"}

    mae = round(sum(abs_errs) / len(abs_errs), 1)
    denom = sum(r["actual_loss_t"] for r in rows) or 1
    return {
        "ok": True,
        "mine_id": mine_id,
        "period": f"{start}..{end}",
        "days": len(rows),
        "mae_t": mae,
        "mape_pct": round(100 * sum(abs_errs) / denom, 1),
        "rows": rows[:60],
    }


@router.get("/capacity")
def get_capacity(
    mine_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"mine_id": mine_id, "capacity_cap_t": capacity_cap(db, mine_id)}
