from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import Report, User
from app.db.session import get_db
from app.deps import get_current_user
from app.schemas.reports import (
    GenerateRequest,
    LineageDetailOut,
    LineageEdgeOut,
    MetricContributionOut,
    ReconciliationOut,
    ReportMetricOut,
    ReportOut,
)
from app.services.aggregation import (
    generate_daily_report,
    generate_higher_report,
    verify_reconciliation,
)
from app.services.audit import append_audit

router = APIRouter(prefix="/reports", tags=["reports"])


def _report_to_out(report: Report) -> ReportOut:
    return ReportOut(
        id=report.id,
        uuid=report.uuid,
        level=report.level,
        mine_id=report.mine_id,
        bench_id=report.bench_id,
        period_start=report.period_start,
        period_end=report.period_end,
        status=report.status,
        version=report.version,
        generated_at=report.generated_at,
        input_hash=report.input_hash,
        expected_children=report.expected_children,
        present_children=report.present_children,
        metrics=[
            ReportMetricOut(
                metric_code=m.metric_code,
                value_int=m.value_int,
                unit=m.unit,
                is_additive=m.is_additive,
            )
            for m in report.metrics
        ],
        lineage_edges=[
            LineageEdgeOut(
                id=e.id,
                child_kind=e.child_kind,
                child_report_id=e.child_report_id,
                child_shift_entry_id=e.child_shift_entry_id,
            )
            for e in report.lineage_edges
        ],
    )


@router.post("/generate", response_model=ReportOut)
def generate_report(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.level == "DAILY":
        if body.bench_id is None:
            raise HTTPException(422, "bench_id required for DAILY reports")
        report = generate_daily_report(
            db, body.mine_id, body.bench_id, body.period_start,
        )
    else:
        report = generate_higher_report(
            db, body.level, body.mine_id, body.bench_id,
            body.period_start, body.period_end,
        )

    if report is None:
        raise HTTPException(
            404, "No data found for the given parameters",
        )

    append_audit(db, user.id, "GENERATE", "REPORT", report.id, {
        "level": body.level,
    })
    db.commit()
    db.refresh(report)
    return _report_to_out(report)


@router.get("", response_model=list[ReportOut])
def list_reports(
    mine_id: int | None = None,
    bench_id: int | None = None,
    level: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    period_start: date | None = None,
    period_end: date | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Report).filter(Report.status != "STALE")
    if mine_id is not None:
        q = q.filter(Report.mine_id == mine_id)
    if bench_id is not None:
        q = q.filter(Report.bench_id == bench_id)
    if level:
        q = q.filter(Report.level == level)
    if status_filter:
        q = q.filter(Report.status == status_filter)
    if period_start:
        q = q.filter(Report.period_start >= period_start)
    if period_end:
        q = q.filter(Report.period_end <= period_end)

    reports = (
        q.order_by(Report.period_start.desc())
        .offset(offset).limit(limit).all()
    )
    return [_report_to_out(r) for r in reports]


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return _report_to_out(report)


@router.get("/{report_id}/reconcile", response_model=ReconciliationOut)
def reconcile_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = verify_reconciliation(db, report_id)
    return ReconciliationOut(**result)


@router.get("/{report_id}/lineage", response_model=LineageDetailOut)
def get_lineage(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    contributions = []
    for rm in report.metrics:
        for c in rm.contributions:
            edge = c.edge
            child_id = (
                edge.child_report_id
                if edge.child_kind == "REPORT"
                else edge.child_shift_entry_id
            )
            contributions.append(MetricContributionOut(
                metric_code=rm.metric_code,
                edge_id=c.edge_id,
                child_kind=edge.child_kind,
                child_id=child_id or 0,
                contributed_value_int=c.contributed_value_int,
            ))

    return LineageDetailOut(
        report_id=report.id,
        level=report.level,
        metrics=[
            ReportMetricOut(
                metric_code=m.metric_code,
                value_int=m.value_int,
                unit=m.unit,
                is_additive=m.is_additive,
            )
            for m in report.metrics
        ],
        edges=[
            LineageEdgeOut(
                id=e.id,
                child_kind=e.child_kind,
                child_report_id=e.child_report_id,
                child_shift_entry_id=e.child_shift_entry_id,
            )
            for e in report.lineage_edges
        ],
        contributions=contributions,
    )
