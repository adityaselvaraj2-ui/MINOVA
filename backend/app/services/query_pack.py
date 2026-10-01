"""Ministry query pack: evidence bundle for a question like
"Why was September production low?" - assembled deterministically,
exportable as PDF. The LLM may only summarise the bundle afterwards.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.extended_models import WeatherDaily
from app.db.models import Document, Mine
from app.services.aggregation import verify_reconciliation
from app.services.targets import target_vs_actual


def build_bundle(db: Session, mine_id: int, start: date, end: date) -> dict:
    mine = db.query(Mine).filter(Mine.id == mine_id).first()
    tva = target_vs_actual(db, mine_id, start, end)

    rain = (
        db.query(WeatherDaily)
        .filter(
            WeatherDaily.mine_id == mine_id,
            WeatherDaily.date >= start,
            WeatherDaily.date <= end,
            WeatherDaily.is_forecast.is_(False),
        )
        .order_by(WeatherDaily.date)
        .all()
    )
    rainy_days = [r for r in rain if r.rain_mm_x10 >= 10]
    total_rain = sum(r.rain_mm_x10 for r in rain) / 10.0

    # Lineage reconciliation for any monthly report covering the period
    from app.db.models import Report
    monthly = (
        db.query(Report)
        .filter(
            Report.mine_id == mine_id,
            Report.level == "MONTHLY",
            Report.period_start <= start,
            Report.period_end >= end,
        )
        .first()
    )
    recon = verify_reconciliation(db, monthly.id) if monthly else {"valid": None}

    docs = (
        db.query(Document)
        .filter(Document.status == "READY")
        .order_by(Document.uploaded_at.desc())
        .limit(10)
        .all()
    )

    return {
        "mine": {"id": mine.id, "code": mine.code, "name": mine.name} if mine else {},
        "period": f"{start} to {end}",
        "generated_at": date.today().isoformat(),
        "target_vs_actual": tva,
        "rainfall": {
            "total_mm": round(total_rain, 1),
            "days_recorded": len(rain),
            "rainy_days_ge10mm": len(rainy_days),
        },
        "lineage_check": recon,
        "source_documents": [
            {"id": d.id, "filename": d.filename, "pages": d.page_count} for d in docs
        ],
    }


def export_bundle_pdf(bundle: dict, out_name: str | None = None) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    styles = getSampleStyleSheet()
    out_dir = settings.exports_path
    out_dir.mkdir(parents=True, exist_ok=True)
    if out_name:
        name = out_name
    else:
        stem = f"query_pack_{bundle['mine'].get('code', 'mine')}"
        safe_period = bundle["period"].replace(" ", "").replace(":", "")
        name = f"{stem}_{safe_period}.pdf"
    out_path = out_dir / name

    story = [
        Paragraph("Ministry Query Pack — Evidence Bundle", styles["Title"]),
        Spacer(1, 6),
        Paragraph(
            f"Mine: {bundle['mine'].get('name', '-')} ({bundle['mine'].get('code', '-')})"
            f" · Period: {bundle['period']} · Generated: {bundle['generated_at']}",
            styles["Normal"],
        ),
        Spacer(1, 10),
    ]

    tva = bundle["target_vs_actual"]
    rows = [
        ["Metric", "Value"],
        ["Target (t)", f"{tva['target_t']:,.0f}" if tva["target_t"] else "—"],
        ["Actual (t)", f"{tva['actual_t']:,.0f}"],
        ["Achievement", (
            f"{tva['achievement_pct']}%"
            if tva["achievement_pct"] is not None else "—"
        )],
        ["vs previous period", (
            f"{tva['delta_vs_prev_pct']}%"
            if tva["delta_vs_prev_pct"] is not None else "—"
        )],
    ]
    for c in tva["top_downtime_causes"]:
        rows.append([f"Downtime: {c['category']}", f"{c['minutes']:,} min"])
    rain = bundle["rainfall"]
    rain_note = (
        f"{rain['total_mm']} mm over {rain['days_recorded']} days "
        f"({rain['rainy_days_ge10mm']} days ≥10 mm)"
    )
    rows.append(["Rainfall (period)", rain_note])

    t = Table(rows, colWidths=[260, 260])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6fa")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Deterministic factual summary", styles["Heading2"]))
    story.append(Paragraph(tva["factual_summary"], styles["Normal"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Lineage reconciliation", styles["Heading2"]))
    rc = bundle["lineage_check"]
    story.append(Paragraph(
        "Valid — leaves sum to stored totals." if rc.get("valid")
        else f"Issues: {rc.get('issues', rc.get('error', 'n/a'))}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Source documents", styles["Heading2"]))
    for d in bundle["source_documents"]:
        story.append(Paragraph(f"• {d['filename']} ({d['pages']} pages)", styles["Normal"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "All figures above are computed deterministically from APPROVED shift "
        "entries and weather records. No AI-generated numbers appear in this "
        "bundle. An LLM may summarise this bundle, but may only reference "
        "figures already present here.",
        styles["Italic"],
    ))

    SimpleDocTemplate(str(out_path), pagesize=A4).build(story)
    return out_path
