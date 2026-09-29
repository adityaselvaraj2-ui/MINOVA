from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import Bench, Equipment, Mine, Role, Subsidiary
from app.db.session import get_db
from app.deps import get_current_user
from app.schemas.masters import BenchOut, EquipmentOut, MineOut, RoleOut, SubsidiaryOut

router = APIRouter(prefix="/masters", tags=["masters"])


@router.get("/subsidiaries", response_model=list[SubsidiaryOut])
def list_subsidiaries(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return db.query(Subsidiary).order_by(Subsidiary.code).all()


@router.get("/mines", response_model=list[MineOut])
def list_mines(
    subsidiary_id: int | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = db.query(Mine)
    if subsidiary_id:
        q = q.filter(Mine.subsidiary_id == subsidiary_id)
    return q.order_by(Mine.code).all()


@router.get("/benches", response_model=list[BenchOut])
def list_benches(
    mine_id: int | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = db.query(Bench)
    if mine_id:
        q = q.filter(Bench.mine_id == mine_id)
    return q.order_by(Bench.code).all()


@router.get("/equipment", response_model=list[EquipmentOut])
def list_equipment(
    mine_id: int | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = db.query(Equipment)
    if mine_id:
        q = q.filter(Equipment.mine_id == mine_id)
    return q.order_by(Equipment.code).all()


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return db.query(Role).order_by(Role.rank).all()
