from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Report, ReportDescription, User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.audit import append_audit
from app.services.factsheet import build_fact_sheet
from app.services.narration import generate_description

router = APIRouter(prefix="/descriptions", tags=["descriptions"])


@router.post("/{report_id}/generate")
def generate(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    fact_sheet = build_fact_sheet(db, report)
    result = generate_description(fact_sheet)

    existing = (
        db.query(ReportDescription)
        .filter(ReportDescription.report_id == report_id)
        .first()
    )
    if existing:
        existing.fact_sheet_json = json.dumps(fact_sheet, default=str)
        existing.text_recorded = result["text_recorded"]
        existing.text_interpretation = result["text_interpretation"]
        existing.model = result["model"]
        existing.prompt_hash = result["prompt_hash"]
        existing.guard_result = result["guard_result"]
        existing.source = result["source"]
        existing.human_reviewed = False
        desc = existing
    else:
        desc = ReportDescription(
            report_id=report_id,
            fact_sheet_json=json.dumps(fact_sheet, default=str),
            text_recorded=result["text_recorded"],
            text_interpretation=result["text_interpretation"],
            model=result["model"],
            prompt_hash=result["prompt_hash"],
            guard_result=result["guard_result"],
            source=result["source"],
        )
        db.add(desc)

    append_audit(db, user.id, "GENERATE_DESC", "REPORT", report_id, {
        "source": result["source"],
        "guard_result": result["guard_result"],
    })
    db.commit()
    db.refresh(desc)

    return {
        "id": desc.id,
        "report_id": desc.report_id,
        "text_recorded": desc.text_recorded,
        "text_interpretation": desc.text_interpretation,
        "model": desc.model,
        "guard_result": desc.guard_result,
        "source": desc.source,
        "human_reviewed": desc.human_reviewed,
        "fact_sheet": json.loads(desc.fact_sheet_json),
    }


@router.get("/{report_id}")
def get_description(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    desc = (
        db.query(ReportDescription)
        .filter(ReportDescription.report_id == report_id)
        .first()
    )
    if not desc:
        raise HTTPException(404, "No description for this report")

    return {
        "id": desc.id,
        "report_id": desc.report_id,
        "text_recorded": desc.text_recorded,
        "text_interpretation": desc.text_interpretation,
        "model": desc.model,
        "guard_result": desc.guard_result,
        "source": desc.source,
        "human_reviewed": desc.human_reviewed,
        "fact_sheet": json.loads(desc.fact_sheet_json),
    }
