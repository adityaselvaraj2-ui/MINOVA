from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
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
    rollup_reports,
    verify_reconciliation,
)
from app.services.audit import append_audit
from app.services.export import export_report

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
    """Generate (or refresh) the report chain bottom-up for the requested
    level and return the top-level report. Falls back to legacy single-level
    behavior when no roll-up data exists."""
    stats = rollup_reports(db, body.mine_id, body.level, body.period_start, body.period_end)

    report = None
    if body.level == "DAILY":
        if body.bench_id is not None:
            report = generate_daily_report(db, body.mine_id, body.bench_id, body.period_start)
    else:
        report = generate_higher_report(
            db, body.level, body.mine_id, body.bench_id,
            body.period_start, body.period_end,
        )

    if report is None:
        raise HTTPException(
            404,
            f"No approved data found for the given parameters (chain: {stats})",
        )

    append_audit(db, user.id, "GENERATE", "REPORT", report.id, {
        "level": body.level,
        "rollup": stats,
        "bench_id": body.bench_id,
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


@router.get("/{report_id}/approval-trail")
def approval_trail(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Prepared by / verified by / approved by chain for the report sources.
    Aggregates distinct actors from approval_action on contributing shift
    entries and their approvers, newest first."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    from sqlalchemy import func

    from app.db.models import ApprovalAction

    shift_ids = [
        e.child_shift_entry_id
        for e in report.lineage_edges
        if e.child_kind == "SHIFT_ENTRY"
    ]
    # include deeper leaves for higher-level reports
    from app.api.lineage import _recursive_children

    for c in _recursive_children(db, report_id):
        if c["child_kind"] == "SHIFT_ENTRY" and c["child_shift_entry_id"]:
            shift_ids.append(c["child_shift_entry_id"])
    shift_ids = sorted(set(shift_ids))

    rows = []
    if shift_ids:
        rows = (
            db.query(
                ApprovalAction.action,
                ApprovalAction.actor_id,
                func.min(ApprovalAction.ts),
                func.max(ApprovalAction.ts),
            )
            .filter(
                ApprovalAction.subject_type == "SHIFT_ENTRY",
                ApprovalAction.subject_id.in_(shift_ids),
            )
            .group_by(ApprovalAction.action, ApprovalAction.actor_id)
            .all()
        )

    from app.db.models import User as DbUser

    actors = {
        u.id: u.full_name
        for u in db.query(DbUser).filter(
            DbUser.id.in_([r[1] for r in rows])
        ).all()
    } if rows else {}

    trail = {
        "SUBMIT": sorted({actors[r[1]] for r in rows if r[0] == "SUBMIT"}),
        "APPROVE": sorted({actors[r[1]] for r in rows if r[0] == "APPROVE"}),
        "RETURN": sorted({actors[r[1]] for r in rows if r[0] == "RETURN"}),
    }
    return {
        "report_id": report_id,
        "prepared_by": trail["SUBMIT"],
        "verified_by": trail["APPROVE"],
        "returned_by": trail["RETURN"],
        "source_entry_count": len(shift_ids),
    }


@router.get("/{report_id}/export")
def export_report_endpoint(
    report_id: int,
    format: str = Query("docx", pattern="^(docx|pdf|xlsx)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    try:
        if format == "xlsx":
            from app.services.export_xlsx import export_report_xlsx

            out_path = export_report_xlsx(db, report)
        else:
            out_path = export_report(db, report, format)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}") from e

    append_audit(db, user.id, "EXPORT", "REPORT", report.id, {"format": format})
    db.commit()

    media = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
    }[format]
    return FileResponse(
        path=out_path,
        media_type=media,
        filename=out_path.name,
    )


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
