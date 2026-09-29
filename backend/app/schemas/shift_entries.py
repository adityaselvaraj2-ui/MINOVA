from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DowntimeEventIn(BaseModel):
    equipment_id: int | None = None
    category: str
    start_min: int = Field(ge=0)
    end_min: int = Field(ge=0)
    cause_text: str | None = None
    evidence_path: str | None = None


class ShiftEntryCreate(BaseModel):
    mine_id: int
    bench_id: int
    work_date: date
    shift_code: str
    planned_min: int = Field(default=480, ge=0)
    workers_present: int = Field(ge=0)
    production_milli_t: int = Field(ge=0)
    ob_milli_m3: int = Field(ge=0)
    weather_code: str | None = None
    rainfall_mm_x10: int | None = None
    temperature_c_x10: int | None = None
    remarks: str | None = None
    downtime_events: list[DowntimeEventIn] = Field(default_factory=list)


class ShiftEntryUpdate(BaseModel):
    planned_min: int | None = None
    workers_present: int | None = None
    production_milli_t: int | None = None
    ob_milli_m3: int | None = None
    weather_code: str | None = None
    rainfall_mm_x10: int | None = None
    temperature_c_x10: int | None = None
    remarks: str | None = None
    downtime_events: list[DowntimeEventIn] | None = None


class ActionComment(BaseModel):
    comment: str = ""


class DowntimeEventOut(BaseModel):
    id: int
    equipment_id: int | None
    category: str
    start_min: int
    end_min: int
    duration_min: int
    cause_text: str | None
    evidence_path: str | None

    model_config = {"from_attributes": True}


class ShiftEntryOut(BaseModel):
    id: int
    uuid: str
    mine_id: int
    bench_id: int
    work_date: date
    shift_code: str
    foreman_id: int
    planned_min: int
    workers_present: int
    production_milli_t: int
    ob_milli_m3: int
    stoppage_min: int
    operating_min: int
    weather_code: str | None
    rainfall_mm_x10: int | None
    temperature_c_x10: int | None
    remarks: str | None
    status: str
    version: int
    supersedes_id: int | None
    current_step: int
    created_at: datetime
    updated_at: datetime
    downtime_events: list[DowntimeEventOut] = []
    warnings: list[str] = []

    model_config = {"from_attributes": True}
