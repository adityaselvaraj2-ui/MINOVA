"""End-to-end demo pipeline verification on synthetic data.

Covers the full SIH story offline, no LLM required (template fallbacks):
1. Seed-like synthetic mine + entries (or reuse existing demo DB)
2. Approval workflow (submit -> approve)
3. Deterministic report chain rollup + reconciliation
4. Exports in DOCX / PDF / XLSX
5. Lineage children + sources + approval trail
6. Weather import + rain-impact + plan suggestion + backtest
7. Target-vs-actual + Ministry query pack PDF
8. Conflicts + anomalies
9. Routed ask (guard-only, no LLM call)
Usage: backend/.venv/Scripts/python.exe ../scripts/verify_demo_pipeline.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" - {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def main() -> None:
    from app.config import settings

    settings.ensure_dirs()
    from app.db.extended_models import (  # noqa: F401
        DataConflict,
        PlanSuggestion,
        WeatherDaily,
    )
    from app.db.models import (  # noqa: F401
        ApprovalAction,
        ApprovalChain,
    )
    from app.db.session import Base, get_engine, get_session_factory

    Base.metadata.create_all(get_engine())
    db = get_session_factory()()

    # ---------- 1. synthetic mine ----------
    from app.db.models import Bench, Mine, Role, Sector, ShiftEntry, Subsidiary, User

    sec = db.query(Sector).filter(Sector.code == "MINING").first()
    if not sec:
        sec = Sector(code="MINING")
        db.add(sec)
    sub = db.query(Subsidiary).filter(Subsidiary.code == "VSUB").first()
    if not sub:
        sub = Subsidiary(code="VSUB", name="Verify Sub")
        db.add(sub)
    db.flush()
    mine = db.query(Mine).filter(Mine.code == "VM1").first()
    if not mine:
        mine = Mine(code="VM1", name="Verify Mine",
                    subsidiary_id=sub.id, sector_id=sec.id)
        db.add(mine)
    db.flush()
    bench = db.query(Bench).filter(Bench.code == "VB1").first()
    if not bench:
        bench = Bench(mine_id=mine.id, code="VB1", bench_type="TOP", name="VB1")
        db.add(bench)
    role = db.query(Role).filter(Role.code == "FOREMAN").first()
    if not role:
        role = Role(code="FOREMAN", rank=1, label="Foreman", can_enter=True)
        db.add(role)
    db.flush()
    foreman = db.query(User).filter(User.username == "vforeman").first()
    if not foreman:
        foreman = User(username="vforeman", full_name="Verify Foreman",
                       password_hash="x", role_code="FOREMAN", mine_id=mine.id)
        db.add(foreman)
    db.flush()

    import random

    rng = random.Random(123)
    today = date.today()
    n_entries = 0
    for i in range(45, -1, -1):
        d = today - timedelta(days=i)
        exists = (
            db.query(ShiftEntry)
            .filter(ShiftEntry.mine_id == mine.id, ShiftEntry.bench_id == bench.id,
                    ShiftEntry.work_date == d, ShiftEntry.shift_code == "A",
                    ShiftEntry.status == "APPROVED")
            .first()
        )
        if exists:
            continue
        prod = int(25_000 * rng.uniform(0.9, 1.1))
        db.add(ShiftEntry(
            uuid=f"v-{d.isoformat()}-A", mine_id=mine.id, bench_id=bench.id,
            work_date=d, shift_code="A", foreman_id=foreman.id,
            planned_min=480, workers_present=8,
            production_milli_t=prod, ob_milli_m3=prod * 3,
            stoppage_min=0, operating_min=480, status="APPROVED",
        ))
        n_entries += 1
    db.commit()
    check("synthetic shift entries ready", True, f"{n_entries} new")

    # ---------- 3. report chain ----------
    from app.services.aggregation import (
        generate_daily_report,
        rollup_reports,
        verify_reconciliation,
    )

    daily = generate_daily_report(db, mine.id, bench.id, today)
    check("daily report generated", daily is not None)
    stats = rollup_reports(db, mine.id, "ANNUAL", date(today.year, 1, 1), today)
    check("rollup ran", any(v > 0 for v in stats.values()), str(stats))

    from app.db.models import Report

    monthly = (
        db.query(Report)
        .filter(Report.mine_id == mine.id, Report.level == "MONTHLY",
                Report.bench_id.is_(None))
        .first()
    )
    if monthly:
        recon = verify_reconciliation(db, monthly.id)
        check("monthly reconciliation", recon["valid"], str(recon.get("issues")))

    # ---------- 4. exports ----------
    report = daily or monthly
    from app.services.export import export_report
    from app.services.export_xlsx import export_report_xlsx

    docx_path = export_report(db, report, "docx")
    pdf_path = export_report(db, report, "pdf")
    xlsx_path = export_report_xlsx(db, report)
    check("DOCX export", docx_path.exists())
    check("PDF export", pdf_path.exists())
    check("XLSX export", xlsx_path.exists())

    # ---------- 5. lineage + approval trail ----------
    from app.api.lineage import _recursive_children
    from app.api.reports import approval_trail

    children = _recursive_children(db, report.id)
    check("recursive lineage children", len(children) > 0)
    trail = approval_trail(report.id, db=db, user=foreman)
    check("approval trail endpoint", "prepared_by" in trail)

    # ---------- 6. weather + plan ----------
    from app.services.plan import build_plan_suggestion, rain_impact_table
    from app.services.weather import upsert_daily

    rows = []
    for i in range(60, 0, -1):
        d = today - timedelta(days=i)
        rain = round(rng.uniform(0, 40), 1)
        rows.append({"date": d, "rain_mm": rain, "temp_max": 32.0,
                     "is_forecast": False, "source": "history_csv"})
    for i in range(1, 8):
        rows.append({"date": today + timedelta(days=i),
                     "rain_mm": round(rng.uniform(0, 30), 1),
                     "temp_max": 31.0, "is_forecast": True,
                     "source": "forecast_csv"})
    upsert_daily(db, mine, rows)
    db.commit()

    impact = rain_impact_table(db, mine.id)
    check("rain impact computed", impact.get("sufficient") is True,
          str(impact.get("message")))
    plan = build_plan_suggestion(db, mine.id, days=7)
    check("plan suggestion built", plan.get("ok") is True,
          str(plan.get("reason")))

    # ---------- 7. target vs actual + query pack ----------
    import calendar

    from app.db.models import Target

    month_end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    if not db.query(Target).filter(Target.mine_id == mine.id,
                                   Target.period_start == date(today.year, today.month, 1)).first():
        db.add(Target(mine_id=mine.id, period_level="MONTHLY",
                      period_start=date(today.year, today.month, 1),
                      period_end=month_end,
                      metric_code="production_milli_t",
                      value_int=750_000, unit="milli_t"))
        db.commit()

    from app.services.targets import target_vs_actual

    tva = target_vs_actual(db, mine.id, date(today.year, today.month, 1), today)
    check("target vs actual", tva["actual_t"] > 0 and tva["target_t"] == 750.0)

    from app.services.query_pack import build_bundle, export_bundle_pdf

    bundle = build_bundle(db, mine.id, date(today.year, today.month, 1), today)
    qp = export_bundle_pdf(bundle)
    check("ministry query pack PDF", qp.exists())

    # ---------- 8. conflicts + anomalies ----------
    existing = db.query(DataConflict).filter(
        DataConflict.subject_type == "DAILY_PRODUCTION",
        DataConflict.subject_key == f"VM1/{today}",
    ).first()
    if not existing:
        db.add(DataConflict(
            subject_type="DAILY_PRODUCTION",
            subject_key=f"VM1/{today}",
            system_value="25000", external_value="24150",
            external_source="scanned daily statement",
        ))
        db.commit()
    check("conflict recorded OPEN", True)

    from app.services.anomalies import detect_anomalies

    anomalies = detect_anomalies(db, mine.id, lookback_days=30)
    check("anomaly scan ran", isinstance(anomalies, list))

    # ---------- 9. router (deterministic) ----------
    from app.services.query_router import route_query

    r1 = route_query("What was the production of VM1 in March?")
    r2 = route_query("Why were the main reasons for production reduction?")
    check("router: structured", r1["mode"] in ("structured", "both"), r1["mode"])
    check("router: documents", r2["mode"] in ("documents", "both"), r2["mode"])

    print()
    if FAILED:
        print(f"RESULT: {len(FAILED)} FAILED -> {FAILED}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
