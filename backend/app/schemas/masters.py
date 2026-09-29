from __future__ import annotations

from pydantic import BaseModel


class SubsidiaryOut(BaseModel):
    id: int
    code: str
    name: str

    model_config = {"from_attributes": True}


class MineOut(BaseModel):
    id: int
    code: str
    name: str
    subsidiary_id: int

    model_config = {"from_attributes": True}


class BenchOut(BaseModel):
    id: int
    code: str
    bench_type: str
    name: str
    mine_id: int

    model_config = {"from_attributes": True}


class EquipmentOut(BaseModel):
    id: int
    code: str
    type: str
    name: str
    mine_id: int

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    code: str
    rank: int
    label: str
    can_enter: bool
    can_approve: bool
    verified: bool

    model_config = {"from_attributes": True}
