from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.analytics import machine_utilization, stoppage_pareto
from app.services.anomalies import detect_anomalies
from app.services.targets import target_vs_actual
from app.services.topics.topics import word_cloud_svg

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stoppage_pareto")
def pareto(
    mine_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return stoppage_pareto(db, start, end)


@router.get("/machine_utilization")
def utilization(
    mine_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return machine_utilization(db, mine_id)


@router.get("/target_vs_actual")
def tva(
    mine_id: int,
    start: date,
    end: date,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return target_vs_actual(db, mine_id, start, end)


@router.get("/word-cloud")
def word_cloud(
    max_terms: int = 60,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Description promise: 'word-cloud generation' over the document corpus.
    Returns an inline-embeddable SVG plus the ranked term list."""
    max_terms = max(10, min(max_terms, 120))
    return word_cloud_svg(db, max_terms=max_terms)


@router.get("/anomalies")
def anomalies(
    mine_id: int,
    lookback_days: int = 45,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"mine_id": mine_id, "anomalies": detect_anomalies(db, mine_id, lookback_days)}
