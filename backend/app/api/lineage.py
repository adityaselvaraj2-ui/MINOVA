from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.db.extended_models import fiscal_year_boundaries
from app.db.models import Report, User
from app.db.session import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/reports", tags=["reports"])


def _recursive_children(db: Session, report_id: int) -> list[dict]:
    """Recursive CTE over lineage_edge (REPORT edges) down to shift entries."""
    sql = """
    WITH RECURSIVE tree AS (
        SELECT le.id AS edge_id, le.parent_report_id, le.child_kind,
               le.child_report_id, le.child_shift_entry_id, 0 AS depth
        FROM lineage_edge le WHERE le.parent_report_id = :rid
        UNION ALL
        SELECT le2.id, le2.parent_report_id, le2.child_kind,
               le2.child_report_id, le2.child_shift_entry_id, t.depth + 1
        FROM lineage_edge le2 JOIN tree t ON le2.parent_report_id = t.child_report_id
    )
    SELECT edge_id, child_kind, child_report_id, child_shift_entry_id, depth
    FROM tree ORDER BY depth, edge_id
    """
    rows = db.execute(sql_text(sql), {"rid": report_id}).fetchall()
    return [
        {
            "edge_id": r[0],
            "child_kind": r[1],
            "child_report_id": r[2],
            "child_shift_entry_id": r[3],
            "depth": r[4],
        }
        for r in rows
    ]


@router.get("/{report_id}/children")
def report_children(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    children = _recursive_children(db, report_id)
    shift_ids = [c["child_shift_entry_id"] for c in children if c["child_kind"] == "SHIFT_ENTRY"]

    entries = []
    if shift_ids:
        from app.db.models import ShiftEntry
        rows = db.query(ShiftEntry).filter(ShiftEntry.id.in_(shift_ids)).all()
        entries = [
            {
                "id": e.id,
                "work_date": str(e.work_date),
                "shift_code": e.shift_code,
                "bench_id": e.bench_id,
                "production_milli_t": e.production_milli_t,
                "ob_milli_m3": e.ob_milli_m3,
                "status": e.status,
                "foreman_id": e.foreman_id,
            }
            for e in rows
        ]
    return {
        "report_id": report_id,
        "level": report.level,
        "count": len(children),
        "children": children,
        "shift_entries": entries,
    }


@router.get("/{report_id}/sources")
def report_sources(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Leaf sources (approved shift entries) with a reconciliation check
    that their production sums to the report's stored production."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    children = _recursive_children(db, report_id)
    leaf_shifts = [
        c["child_shift_entry_id"] for c in children
        if c["child_kind"] == "SHIFT_ENTRY"
    ]
    leaf_reports = {c["child_report_id"] for c in children if c["child_kind"] == "REPORT"}
    _ = leaf_reports  # retained for future per-level leaf reporting

    from app.db.models import ShiftEntry
    entries = (
        db.query(ShiftEntry)
        .filter(ShiftEntry.id.in_(leaf_shifts) if leaf_shifts else ShiftEntry.id == -1)
        .all()
    )
    leaf_sum = sum(e.production_milli_t for e in entries)
    prod_metric = next(
        (m.value_int for m in report.metrics if m.metric_code == "production_milli_t"),
        None,
    )
    # For higher-level reports the direct leaf sum equals the stored total only
    # when the tree is complete; report the check honestly either way.
    reconciled = (prod_metric is None) or (leaf_sum == prod_metric)

    return {
        "report_id": report_id,
        "level": report.level,
        "leaf_shift_entries": [
            {
                "id": e.id,
                "work_date": str(e.work_date),
                "shift_code": e.shift_code,
                "bench_id": e.bench_id,
                "production_t": e.production_milli_t / 1000.0,
                "foreman_id": e.foreman_id,
                "status": e.status,
            }
            for e in entries
        ],
        "leaf_shift_count": len(entries),
        "leaf_production_milli_t": leaf_sum,
        "stored_production_milli_t": prod_metric,
        "reconciled": reconciled,
        "note": (
            "Direct-leaf sum equals stored total" if reconciled
            else "Leaf sum differs from stored total (intermediate report "
            "levels aggregate their own children; use /lineage for per-edge "
            "contributions)"
        ),
    }


@router.get("/fiscal-year/{year}")
def fiscal_year(
    year: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start, end = fiscal_year_boundaries(year)
    reports = (
        db.query(Report)
        .filter(
            Report.mine_id.isnot(None),
            Report.period_start >= start,
            Report.period_end <= end,
            Report.status != "STALE",
        )
        .all()
    )
    return {
        "fiscal_year": f"FY{year}-{str(year + 1)[-2:]}",
        "start": str(start),
        "end": str(end),
        "report_count": len(reports),
    }
