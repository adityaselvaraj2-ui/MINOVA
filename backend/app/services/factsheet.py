from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.db.models import Report, Target
from app.services.units import compute_percentage, compute_ratio, milli_to_display


def build_fact_sheet(db: Session, report: Report) -> dict:
    metrics = {m.metric_code: m.value_int for m in report.metrics}

    prod = metrics.get("production_milli_t", 0)
    ob = metrics.get("ob_milli_m3", 0)
    planned = metrics.get("planned_min", 0)
    operating = metrics.get("operating_min", 0)
    stoppage = metrics.get("stoppage_min", 0)
    workers = metrics.get("workers_present", 0)

    facts: dict = {
        "report_level": report.level,
        "mine_id": report.mine_id,
        "bench_id": report.bench_id,
        "period_start": str(report.period_start),
        "period_end": str(report.period_end),
        "coverage": f"{report.present_children}/{report.expected_children}",
        "production_t": milli_to_display(prod),
        "overburden_m3": milli_to_display(ob),
        "planned_min": planned,
        "operating_min": operating,
        "stoppage_min": stoppage,
        "workers_present": workers,
        "availability_pct": compute_percentage(operating, planned) or "0.00",
        "stripping_ratio": compute_ratio(ob, prod) or "0.0000",
    }

    targets = (
        db.query(Target)
        .filter(
            Target.mine_id == report.mine_id,
            Target.period_start <= report.period_start,
            Target.period_end >= report.period_end,
        )
        .all()
    )
    if targets:
        facts["targets"] = {
            t.metric_code: {
                "value": t.value_int,
                "unit": t.unit,
                "period": f"{t.period_start} to {t.period_end}",
            }
            for t in targets
        }

    _allowed = set()
    for v in facts.values():
        if isinstance(v, (int, float)):
            _allowed.add(str(v))
        elif isinstance(v, str):
            _allowed.add(v)
    facts["_allowed_numbers"] = sorted(_allowed)

    return facts


def fact_sheet_to_prompt_block(facts: dict) -> str:
    clean = {k: v for k, v in facts.items() if not k.startswith("_")}
    return (
        "=== FACT SHEET (authoritative numbers) ===\n"
        + json.dumps(clean, indent=2)
        + "\n=== END FACT SHEET ==="
    )
