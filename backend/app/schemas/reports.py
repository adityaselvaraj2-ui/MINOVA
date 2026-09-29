from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    level: str
    mine_id: int
    bench_id: int | None = None
    period_start: date
    period_end: date


class ReportMetricOut(BaseModel):
    metric_code: str
    value_int: int
    unit: str
    is_additive: bool


class LineageEdgeOut(BaseModel):
    id: int
    child_kind: str
    child_report_id: int | None = None
    child_shift_entry_id: int | None = None


class ReportOut(BaseModel):
    id: int
    uuid: str
    level: str
    mine_id: int
    bench_id: int | None = None
    period_start: date
    period_end: date
    status: str
    version: int
    generated_at: datetime | None = None
    input_hash: str | None = None
    expected_children: int
    present_children: int
    metrics: list[ReportMetricOut] = []
    lineage_edges: list[LineageEdgeOut] = []


class ReconciliationOut(BaseModel):
    valid: bool
    report_id: int | None = None
    level: str | None = None
    expected_children: int = 0
    present_children: int = 0
    edge_count: int = 0
    issues: list[str] = []
    error: str | None = None


class MetricContributionOut(BaseModel):
    metric_code: str
    edge_id: int
    child_kind: str
    child_id: int
    contributed_value_int: int


class LineageDetailOut(BaseModel):
    report_id: int
    level: str
    metrics: list[ReportMetricOut]
    edges: list[LineageEdgeOut]
    contributions: list[MetricContributionOut]
