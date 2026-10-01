from __future__ import annotations

import hashlib
import json
import uuid as uuid_mod
from datetime import date

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    Bench,
    LineageEdge,
    MetricContribution,
    Report,
    ReportMetric,
    ShiftEntry,
)
from app.services.periods import (
    CHILD_LEVEL,
    child_periods,
    month_boundaries,
    month_clipped_weeks,
    quarter_boundaries,
    quarter_for_month,
)

ADDITIVE_METRICS = {
    "production_milli_t": "milli_t",
    "ob_milli_m3": "milli_m3",
    "planned_min": "min",
    "operating_min": "min",
    "stoppage_min": "min",
    "workers_present": "count",
}

DERIVED_METRICS = {
    "stripping_ratio_x1000": "ratio_x1000",
    "availability_bp": "bp",
}


def _input_hash_for_entries(entries: list[ShiftEntry]) -> str:
    ids = sorted(e.id for e in entries)
    versions = sorted((e.id, e.version) for e in entries)
    payload = json.dumps({"ids": ids, "versions": versions})
    return hashlib.sha256(payload.encode()).hexdigest()


def _input_hash_for_reports(reports: list[Report]) -> str:
    ids = sorted(r.id for r in reports)
    hashes = sorted((r.id, r.input_hash or "") for r in reports)
    payload = json.dumps({"ids": ids, "hashes": hashes})
    return hashlib.sha256(payload.encode()).hexdigest()


def _compute_derived(totals: dict[str, int]) -> dict[str, int]:
    derived = {}
    prod = totals.get("production_milli_t", 0)
    ob = totals.get("ob_milli_m3", 0)
    planned = totals.get("planned_min", 0)
    operating = totals.get("operating_min", 0)

    if prod > 0:
        derived["stripping_ratio_x1000"] = (ob * 1000) // prod
    else:
        derived["stripping_ratio_x1000"] = 0

    if planned > 0:
        derived["availability_bp"] = (operating * 10000) // planned
    else:
        derived["availability_bp"] = 0

    return derived


def _find_existing(
    db: Session, level: str, mine_id: int, bench_id: int | None,
    period_start, period_end,
) -> Report | None:
    q = db.query(Report).filter(
        Report.level == level,
        Report.mine_id == mine_id,
        Report.period_start == period_start,
        Report.period_end == period_end,
        Report.status != "STALE",
    )
    if bench_id is not None:
        q = q.filter(Report.bench_id == bench_id)
    else:
        q = q.filter(Report.bench_id.is_(None))
    return q.first()


def _clear_report_children(db: Session, report_id: int) -> None:
    edges = db.query(LineageEdge).filter(
        LineageEdge.parent_report_id == report_id,
    ).all()
    for edge in edges:
        db.query(MetricContribution).filter(
            MetricContribution.edge_id == edge.id,
        ).delete()
    db.query(LineageEdge).filter(
        LineageEdge.parent_report_id == report_id,
    ).delete()
    db.query(ReportMetric).filter(
        ReportMetric.report_id == report_id,
    ).delete()


def generate_daily_report(
    db: Session, mine_id: int, bench_id: int, work_date,
) -> Report | None:
    entries = (
        db.query(ShiftEntry)
        .filter(
            ShiftEntry.mine_id == mine_id,
            ShiftEntry.bench_id == bench_id,
            ShiftEntry.work_date == work_date,
            ShiftEntry.status == "APPROVED",
        )
        .all()
    )
    if not entries:
        return None

    input_hash = _input_hash_for_entries(entries)
    existing = _find_existing(db, "DAILY", mine_id, bench_id, work_date, work_date)

    if existing and existing.input_hash == input_hash:
        return existing

    if existing:
        _clear_report_children(db, existing.id)
        report = existing
        report.input_hash = input_hash
        report.present_children = len(entries)
        report.expected_children = len(settings.shift_codes)
        report.version += 1
        report.status = "DRAFT"
    else:
        report = Report(
            uuid=str(uuid_mod.uuid4()),
            level="DAILY",
            mine_id=mine_id,
            bench_id=bench_id,
            period_start=work_date,
            period_end=work_date,
            input_hash=input_hash,
            expected_children=len(settings.shift_codes),
            present_children=len(entries),
        )
        db.add(report)
    db.flush()

    totals: dict[str, int] = {m: 0 for m in ADDITIVE_METRICS}
    edges: list[tuple[LineageEdge, ShiftEntry]] = []

    for entry in entries:
        edge = LineageEdge(
            parent_report_id=report.id,
            child_kind="SHIFT_ENTRY",
            child_shift_entry_id=entry.id,
        )
        db.add(edge)
        db.flush()
        edges.append((edge, entry))
        for mc in ADDITIVE_METRICS:
            totals[mc] += getattr(entry, mc)

    metrics_map: dict[str, ReportMetric] = {}
    for mc, unit in ADDITIVE_METRICS.items():
        rm = ReportMetric(
            report_id=report.id,
            metric_code=mc,
            value_int=totals[mc],
            unit=unit,
            is_additive=True,
        )
        db.add(rm)
        db.flush()
        metrics_map[mc] = rm

    for edge, entry in edges:
        for mc in ADDITIVE_METRICS:
            db.add(MetricContribution(
                parent_metric_id=metrics_map[mc].id,
                edge_id=edge.id,
                contributed_value_int=getattr(entry, mc),
            ))

    derived = _compute_derived(totals)
    for mc, val in derived.items():
        db.add(ReportMetric(
            report_id=report.id,
            metric_code=mc,
            value_int=val,
            unit=DERIVED_METRICS[mc],
            is_additive=False,
        ))

    db.flush()
    return report


def generate_higher_report(
    db: Session, level: str, mine_id: int, bench_id: int | None,
    period_start, period_end,
) -> Report | None:
    child_level = CHILD_LEVEL.get(level)
    if not child_level:
        return None

    periods = child_periods(level, period_start, period_end)
    child_reports: list[Report] = []

    for ps, pe in periods:
        q = db.query(Report).filter(
            Report.level == child_level,
            Report.mine_id == mine_id,
            Report.period_start == ps,
            Report.period_end == pe,
            Report.status != "STALE",
        )
        if bench_id is not None:
            q = q.filter(Report.bench_id == bench_id)
        else:
            q = q.filter(Report.bench_id.is_(None))
        cr = q.first()
        if cr:
            child_reports.append(cr)

    if not child_reports:
        return None

    input_hash = _input_hash_for_reports(child_reports)
    existing = _find_existing(db, level, mine_id, bench_id, period_start, period_end)

    if existing and existing.input_hash == input_hash:
        return existing

    if existing:
        _clear_report_children(db, existing.id)
        report = existing
        report.input_hash = input_hash
        report.present_children = len(child_reports)
        report.expected_children = len(periods)
        report.version += 1
        report.status = "DRAFT"
    else:
        report = Report(
            uuid=str(uuid_mod.uuid4()),
            level=level,
            mine_id=mine_id,
            bench_id=bench_id,
            period_start=period_start,
            period_end=period_end,
            input_hash=input_hash,
            expected_children=len(periods),
            present_children=len(child_reports),
        )
        db.add(report)
    db.flush()

    totals: dict[str, int] = {m: 0 for m in ADDITIVE_METRICS}
    edges: list[tuple[LineageEdge, Report]] = []

    for cr in child_reports:
        edge = LineageEdge(
            parent_report_id=report.id,
            child_kind="REPORT",
            child_report_id=cr.id,
        )
        db.add(edge)
        db.flush()
        edges.append((edge, cr))

        for rm in cr.metrics:
            if rm.is_additive and rm.metric_code in totals:
                totals[rm.metric_code] += rm.value_int

    metrics_map: dict[str, ReportMetric] = {}
    for mc, unit in ADDITIVE_METRICS.items():
        rm = ReportMetric(
            report_id=report.id,
            metric_code=mc,
            value_int=totals[mc],
            unit=unit,
            is_additive=True,
        )
        db.add(rm)
        db.flush()
        metrics_map[mc] = rm

    for edge, cr in edges:
        child_metrics = {m.metric_code: m.value_int for m in cr.metrics}
        for mc in ADDITIVE_METRICS:
            db.add(MetricContribution(
                parent_metric_id=metrics_map[mc].id,
                edge_id=edge.id,
                contributed_value_int=child_metrics.get(mc, 0),
            ))

    derived = _compute_derived(totals)
    for mc, val in derived.items():
        db.add(ReportMetric(
            report_id=report.id,
            metric_code=mc,
            value_int=val,
            unit=DERIVED_METRICS[mc],
            is_additive=False,
        ))

    db.flush()
    return report


def generate_mine_daily_report(
    db: Session, mine_id: int, work_date,
) -> Report | None:
    """Mine-level DAILY: aggregates the bench-level DAILY reports for the
date. Needed because shift entries are bench-scoped, while mine-level
higher reports (WEEKLY+) aggregate mine-level children."""
    bench_dailies = (
        db.query(Report)
        .filter(
            Report.level == "DAILY",
            Report.mine_id == mine_id,
            Report.bench_id.isnot(None),
            Report.period_start == work_date,
            Report.period_end == work_date,
            Report.status != "STALE",
        )
        .all()
    )
    if not bench_dailies:
        return None

    input_hash = _input_hash_for_reports(bench_dailies)
    existing = _find_existing(db, "DAILY", mine_id, None, work_date, work_date)

    if existing and existing.input_hash == input_hash:
        return existing

    if existing:
        _clear_report_children(db, existing.id)
        report = existing
        report.input_hash = input_hash
        report.present_children = len(bench_dailies)
        report.expected_children = len(bench_dailies)
        report.version += 1
        report.status = "DRAFT"
    else:
        report = Report(
            uuid=str(uuid_mod.uuid4()),
            level="DAILY",
            mine_id=mine_id,
            bench_id=None,
            period_start=work_date,
            period_end=work_date,
            input_hash=input_hash,
            expected_children=len(bench_dailies),
            present_children=len(bench_dailies),
        )
        db.add(report)
    db.flush()

    totals: dict[str, int] = {m: 0 for m in ADDITIVE_METRICS}
    metrics_map: dict[str, ReportMetric] = {}
    for mc, unit in ADDITIVE_METRICS.items():
        rm = ReportMetric(
            report_id=report.id,
            metric_code=mc,
            value_int=0,
            unit=unit,
            is_additive=True,
        )
        db.add(rm)
        db.flush()
        metrics_map[mc] = rm

    for child in bench_dailies:
        edge = LineageEdge(
            parent_report_id=report.id,
            child_kind="REPORT",
            child_report_id=child.id,
        )
        db.add(edge)
        db.flush()
        child_metrics = {m.metric_code: m.value_int for m in child.metrics}
        for mc in ADDITIVE_METRICS:
            value = child_metrics.get(mc, 0)
            totals[mc] += value
            db.add(MetricContribution(
                parent_metric_id=metrics_map[mc].id,
                edge_id=edge.id,
                contributed_value_int=value,
            ))

    for mc, rm in metrics_map.items():
        rm.value_int = totals[mc]

    derived = _compute_derived(totals)
    for mc, val in derived.items():
        db.add(ReportMetric(
            report_id=report.id,
            metric_code=mc,
            value_int=val,
            unit=DERIVED_METRICS[mc],
            is_additive=False,
        ))

    db.flush()
    return report


def _months_between(period_start, period_end) -> list[tuple[int, int]]:
    y, m = period_start.year, period_start.month
    out: list[tuple[int, int]] = []
    while (y, m) <= (period_end.year, period_end.month):
        out.append((y, m))
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def rollup_reports(
    db: Session, mine_id: int, level: str, period_start, period_end,
) -> dict:
    """Generate the full report chain bottom-up for a mine over a period.

    Creates DAILY reports from APPROVED shift entries, then WEEKLY from
    DAILYs, then MONTHLY from WEEKLYs (etc.) — both per bench and at
    mine level (bench_id NULL). Idempotent: unchanged inputs reuse
    existing reports via input_hash.
    """
    stats = {
        "DAILY": 0, "WEEKLY": 0, "MONTHLY": 0,
        "QUARTERLY": 0, "HALF_YEARLY": 0, "ANNUAL": 0,
    }

    def chain(bench_id: int | None, include_daily: bool) -> None:
        if include_daily:
            d = period_start
            while d <= period_end:
                if bench_id is None:
                    daily = generate_mine_daily_report(db, mine_id, d)
                else:
                    daily = generate_daily_report(db, mine_id, bench_id, d)
                if daily:
                    stats["DAILY"] += 1
                d = date.fromordinal(d.toordinal() + 1)

        for (y, m) in _months_between(period_start, period_end):
            for ws, we in month_clipped_weeks(y, m):
                overlap = we >= period_start and ws <= period_end
                if overlap and generate_higher_report(db, "WEEKLY", mine_id, bench_id, ws, we):
                    stats["WEEKLY"] += 1

        if level in ("MONTHLY", "QUARTERLY", "HALF_YEARLY", "ANNUAL"):
            for (y, m) in _months_between(period_start, period_end):
                ms, me = month_boundaries(y, m)
                overlap = me >= period_start and ms <= period_end
                if overlap and generate_higher_report(db, "MONTHLY", mine_id, bench_id, ms, me):
                    stats["MONTHLY"] += 1

        if level in ("QUARTERLY", "ANNUAL"):
            for (y, m) in _months_between(period_start, period_end):
                qs, qe = quarter_boundaries(y, quarter_for_month(m))
                overlap = qe >= period_start and qs <= period_end
                if overlap and generate_higher_report(db, "QUARTERLY", mine_id, bench_id, qs, qe):
                    stats["QUARTERLY"] += 1

        if level == "HALF_YEARLY":
            hy = generate_higher_report(
                db, "HALF_YEARLY", mine_id, bench_id, period_start, period_end,
            )
            if hy:
                stats["HALF_YEARLY"] += 1

        if level == "ANNUAL":
            ann = generate_higher_report(
                db, "ANNUAL", mine_id, bench_id, period_start, period_end,
            )
            if ann:
                stats["ANNUAL"] += 1

    benches = [
        b.id for b in db.query(Bench).filter(Bench.mine_id == mine_id).all()
    ]
    for bench_id in benches:
        chain(bench_id, include_daily=True)
    chain(None, include_daily=True)

    return stats


def verify_reconciliation(
    db: Session, report_id: int,
) -> dict:
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return {"valid": False, "error": "Report not found"}

    edges = report.lineage_edges
    issues: list[str] = []

    for rm in report.metrics:
        if not rm.is_additive:
            continue
        contrib_sum = sum(c.contributed_value_int for c in rm.contributions)
        if contrib_sum != rm.value_int:
            issues.append(
                f"{rm.metric_code}: contributions sum to {contrib_sum} "
                f"but metric value is {rm.value_int}"
            )

    if report.present_children != len(edges):
        issues.append(
            f"present_children={report.present_children} but "
            f"{len(edges)} lineage edges found"
        )

    return {
        "valid": len(issues) == 0,
        "report_id": report_id,
        "level": report.level,
        "expected_children": report.expected_children,
        "present_children": report.present_children,
        "edge_count": len(edges),
        "issues": issues,
    }
