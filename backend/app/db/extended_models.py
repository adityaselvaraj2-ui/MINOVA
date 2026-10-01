from __future__ import annotations

import calendar
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db.session import Base


class WeatherDaily(Base):
    __tablename__ = "weather_daily"

    id: Mapped[int] = mapped_column(primary_key=True)
    mine_id: Mapped[int] = mapped_column(ForeignKey("mine.id"), nullable=False)
    date: Mapped[date] = mapped_column(nullable=False)
    rain_mm_x10: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    temp_max_x10: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="history_csv")
    is_forecast: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("mine_id", "date", name="uq_weather_mine_date"),
        Index("ix_weather_mine_date", "mine_id", "date"),
    )


class PlanSuggestion(Base):
    __tablename__ = "plan_suggestion"

    id: Mapped[int] = mapped_column(primary_key=True)
    mine_id: Mapped[int] = mapped_column(ForeignKey("mine.id"), nullable=False)
    horizon_start: Mapped[date] = mapped_column(nullable=False)
    horizon_end: Mapped[date] = mapped_column(nullable=False)
    payload_json: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("status IN ('PENDING','ACCEPTED','REJECTED')"),
        nullable=False,
        default="PENDING",
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_plan_suggestion_mine", "mine_id"),)


class DataConflict(Base):
    """Cross-source discrepancy flagged for HUMAN verification.

    The system never decides which value is correct (abstract commitment):
    e.g. computed 8,000 t vs another document stating 7,850 t.
    """
    __tablename__ = "data_conflict"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False)  # DAILY_PRODUCTION etc
    subject_key: Mapped[str] = mapped_column(String(120), nullable=False)  # mine/date
    system_value: Mapped[str] = mapped_column(String(50), nullable=False)
    external_value: Mapped[str] = mapped_column(String(50), nullable=False)
    external_source: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12),
        CheckConstraint("status IN ('OPEN','RESOLVED_SYSTEM','RESOLVED_EXTERNAL')"),
        nullable=False,
        default="OPEN",
    )
    resolution_note: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("subject_type", "subject_key", "external_source",
                         name="uq_conflict_subject_source"),
        Index("ix_conflict_status", "status"),
    )


def fiscal_year_boundaries(year: int, start_month: int | None = None) -> tuple[date, date]:
    """Indian FY default (Apr-Mar), configurable via fiscal_year_start_month."""
    m = start_month if start_month is not None else settings.fiscal_year_start_month
    start = date(year, m, 1)
    end_month = m - 1 if m > 1 else 12
    end_year = year + 1 if m > 1 else year
    end = date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
    return start, end
