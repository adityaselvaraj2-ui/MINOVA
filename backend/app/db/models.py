from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Subsidiary(Base):
    __tablename__ = "subsidiary"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    mines: Mapped[list[Mine]] = relationship(back_populates="subsidiary")


class Sector(Base):
    __tablename__ = "sector"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("code IN ('MINING','POWER','WATER','BRICKS','OTHER')"),
        unique=True,
        nullable=False,
    )


class Mine(Base):
    __tablename__ = "mine"

    id: Mapped[int] = mapped_column(primary_key=True)
    subsidiary_id: Mapped[int] = mapped_column(ForeignKey("subsidiary.id"), nullable=False)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sector.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    subsidiary: Mapped[Subsidiary] = relationship(back_populates="mines")
    benches: Mapped[list[Bench]] = relationship(back_populates="mine")
    equipment: Mapped[list[Equipment]] = relationship(back_populates="mine")

    __table_args__ = (
        Index("ix_mine_subsidiary", "subsidiary_id"),
        Index("ix_mine_sector", "sector_id"),
    )


class Bench(Base):
    __tablename__ = "bench"

    id: Mapped[int] = mapped_column(primary_key=True)
    mine_id: Mapped[int] = mapped_column(ForeignKey("mine.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    bench_type: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("bench_type IN ('SURFACE','TOP','MIDDLE','BOTTOM')"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    mine: Mapped[Mine] = relationship(back_populates="benches")

    __table_args__ = (
        Index("ix_bench_mine", "mine_id"),
        UniqueConstraint("mine_id", "code", name="uq_bench_mine_code"),
    )


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    mine_id: Mapped[int] = mapped_column(ForeignKey("mine.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    mine: Mapped[Mine] = relationship(back_populates="equipment")

    __table_args__ = (Index("ix_equipment_mine", "mine_id"),)


class Role(Base):
    __tablename__ = "role"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    can_enter: Mapped[bool] = mapped_column(Boolean, default=False)
    can_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role_code: Mapped[str] = mapped_column(ForeignKey("role.code"), nullable=False)
    mine_id: Mapped[int | None] = mapped_column(ForeignKey("mine.id"), nullable=True)
    department: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    role: Mapped[Role] = relationship()
    mine: Mapped[Mine | None] = relationship()

    __table_args__ = (
        Index("ix_user_role", "role_code"),
        Index("ix_user_mine", "mine_id"),
    )


class ApprovalChain(Base):
    __tablename__ = "approval_chain"

    id: Mapped[int] = mapped_column(primary_key=True)
    mine_id: Mapped[int | None] = mapped_column(ForeignKey("mine.id"), nullable=True)
    report_level: Mapped[str] = mapped_column(String(20), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    role_code: Mapped[str] = mapped_column(ForeignKey("role.code"), nullable=False)

    __table_args__ = (
        Index("ix_approval_chain_mine", "mine_id"),
        UniqueConstraint("mine_id", "report_level", "step_order", name="uq_approval_chain_step"),
    )


class ShiftEntry(Base):
    __tablename__ = "shift_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    mine_id: Mapped[int] = mapped_column(ForeignKey("mine.id"), nullable=False)
    bench_id: Mapped[int] = mapped_column(ForeignKey("bench.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(nullable=False)
    shift_code: Mapped[str] = mapped_column(
        String(1),
        CheckConstraint("shift_code IN ('A','B','C')"),
        nullable=False,
    )
    foreman_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    planned_min: Mapped[int] = mapped_column(Integer, nullable=False)
    workers_present: Mapped[int] = mapped_column(Integer, nullable=False)
    production_milli_t: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ob_milli_m3: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stoppage_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    operating_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weather_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rainfall_mm_x10: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature_c_x10: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','RETURNED','APPROVED','SUPERSEDED')"),
        nullable=False,
        default="DRAFT",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("shift_entry.id"), nullable=True
    )
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    downtime_events: Mapped[list[DowntimeEvent]] = relationship(back_populates="shift_entry")

    __table_args__ = (
        Index(
            "ix_shift_entry_mine_bench_date_shift",
            "mine_id", "bench_id", "work_date", "shift_code",
        ),
        Index("ix_shift_entry_mine", "mine_id"),
        Index("ix_shift_entry_bench", "bench_id"),
        Index("ix_shift_entry_foreman", "foreman_id"),
        Index("ix_shift_entry_status", "status"),
        UniqueConstraint(
            "mine_id", "bench_id", "work_date", "shift_code", "version",
            name="uq_shift_entry_unique_version",
        ),
    )


DOWNTIME_CATEGORIES = (
    "EQUIPMENT_FAILURE",
    "SCHEDULED_MAINTENANCE",
    "WEATHER",
    "FIRE_INCIDENT",
    "LABOUR",
    "SUPPLY",
    "OTHER",
)


class DowntimeEvent(Base):
    __tablename__ = "downtime_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_entry_id: Mapped[int] = mapped_column(ForeignKey("shift_entry.id"), nullable=False)
    equipment_id: Mapped[int | None] = mapped_column(ForeignKey("equipment.id"), nullable=True)
    category: Mapped[str] = mapped_column(
        String(30),
        CheckConstraint(
            "category IN ('EQUIPMENT_FAILURE','SCHEDULED_MAINTENANCE','WEATHER',"
            "'FIRE_INCIDENT','LABOUR','SUPPLY','OTHER')"
        ),
        nullable=False,
    )
    start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    cause_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    shift_entry: Mapped[ShiftEntry] = relationship(back_populates="downtime_events")

    __table_args__ = (Index("ix_downtime_shift_entry", "shift_entry_id"),)


class Target(Base):
    __tablename__ = "target"

    id: Mapped[int] = mapped_column(primary_key=True)
    mine_id: Mapped[int] = mapped_column(ForeignKey("mine.id"), nullable=False)
    bench_id: Mapped[int | None] = mapped_column(ForeignKey("bench.id"), nullable=True)
    period_level: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    metric_code: Mapped[str] = mapped_column(String(30), nullable=False)
    value_int: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_target_id: Mapped[int | None] = mapped_column(
        ForeignKey("target.id"), nullable=True
    )
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_target_mine", "mine_id"),
        Index("ix_target_bench", "bench_id"),
        Index("ix_target_period", "period_level", "period_start", "period_end"),
    )


class Report(Base):
    __tablename__ = "report"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    level: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "level IN ('DAILY','WEEKLY','MONTHLY','QUARTERLY','HALF_YEARLY','ANNUAL')"
        ),
        nullable=False,
    )
    mine_id: Mapped[int] = mapped_column(ForeignKey("mine.id"), nullable=False)
    bench_id: Mapped[int | None] = mapped_column(ForeignKey("bench.id"), nullable=True)
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','RETURNED','APPROVED','STALE')"),
        nullable=False,
        default="DRAFT",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    generator_version: Mapped[str] = mapped_column(String(20), default="0.1.0")
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_children: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    present_children: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    metrics: Mapped[list[ReportMetric]] = relationship(back_populates="report")
    lineage_edges: Mapped[list[LineageEdge]] = relationship(
        back_populates="parent_report", foreign_keys="LineageEdge.parent_report_id"
    )
    description: Mapped[ReportDescription | None] = relationship(
        back_populates="report", uselist=False
    )

    __table_args__ = (
        Index("ix_report_mine", "mine_id"),
        Index("ix_report_bench", "bench_id"),
        Index("ix_report_level_period", "level", "period_start", "period_end"),
        Index("ix_report_status", "status"),
    )


class ReportMetric(Base):
    __tablename__ = "report_metric"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"), nullable=False)
    metric_code: Mapped[str] = mapped_column(String(30), nullable=False)
    value_int: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    is_additive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    report: Mapped[Report] = relationship(back_populates="metrics")
    contributions: Mapped[list[MetricContribution]] = relationship(back_populates="parent_metric")

    __table_args__ = (
        Index("ix_report_metric_report", "report_id"),
        UniqueConstraint("report_id", "metric_code", name="uq_report_metric"),
    )


class LineageEdge(Base):
    __tablename__ = "lineage_edge"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_report_id: Mapped[int] = mapped_column(ForeignKey("report.id"), nullable=False)
    child_kind: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("child_kind IN ('REPORT','SHIFT_ENTRY')"),
        nullable=False,
    )
    child_report_id: Mapped[int | None] = mapped_column(ForeignKey("report.id"), nullable=True)
    child_shift_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("shift_entry.id"), nullable=True
    )

    parent_report: Mapped[Report] = relationship(
        back_populates="lineage_edges", foreign_keys=[parent_report_id]
    )
    contributions: Mapped[list[MetricContribution]] = relationship(back_populates="edge")

    __table_args__ = (
        Index("ix_lineage_parent", "parent_report_id"),
        Index("ix_lineage_child_report", "child_report_id"),
        Index("ix_lineage_child_shift", "child_shift_entry_id"),
        CheckConstraint(
            "(child_report_id IS NOT NULL AND child_shift_entry_id IS NULL) OR "
            "(child_report_id IS NULL AND child_shift_entry_id IS NOT NULL)",
            name="ck_lineage_exactly_one_child",
        ),
    )


class MetricContribution(Base):
    __tablename__ = "metric_contribution"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_metric_id: Mapped[int] = mapped_column(ForeignKey("report_metric.id"), nullable=False)
    edge_id: Mapped[int] = mapped_column(ForeignKey("lineage_edge.id"), nullable=False)
    contributed_value_int: Mapped[int] = mapped_column(Integer, nullable=False)

    parent_metric: Mapped[ReportMetric] = relationship(back_populates="contributions")
    edge: Mapped[LineageEdge] = relationship(back_populates="contributions")

    __table_args__ = (
        Index("ix_contribution_metric", "parent_metric_id"),
        Index("ix_contribution_edge", "edge_id"),
    )


class ReportDescription(Base):
    __tablename__ = "report_description"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"), unique=True, nullable=False)
    fact_sheet_json: Mapped[str] = mapped_column(Text, nullable=False)
    text_recorded: Mapped[str] = mapped_column(Text, nullable=False, default="")
    text_interpretation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    guard_result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("source IN ('LLM','TEMPLATE_FALLBACK')"),
        nullable=False,
        default="TEMPLATE_FALLBACK",
    )
    human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)

    report: Mapped[Report] = relationship(back_populates="description")


class ApprovalAction(Base):
    __tablename__ = "approval_action"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    action: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("action IN ('SUBMIT','APPROVE','RETURN')"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_approval_action_subject", "subject_type", "subject_id"),
        Index("ix_approval_action_actor", "actor_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_audit_subject", "subject_type", "subject_id"),
        Index("ix_audit_actor", "actor_id"),
        Index("ix_audit_ts", "ts"),
    )


class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("status IN ('UPLOADED','PROCESSING','READY','ERROR')"),
        default="UPLOADED",
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document")

    __table_args__ = (
        Index("ix_document_status", "status"),
        Index("ix_document_uploader", "uploaded_by"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunk"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    chroma_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunk_document", "document_id"),
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_idx"),
    )
