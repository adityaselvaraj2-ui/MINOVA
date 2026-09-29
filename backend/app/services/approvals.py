from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import ApprovalAction, ApprovalChain, ShiftEntry, User
from app.services.audit import append_audit


def get_approval_chain(db: Session, mine_id: int, level: str = "DAILY") -> list[ApprovalChain]:
    return (
        db.query(ApprovalChain)
        .filter(
            (ApprovalChain.mine_id == mine_id) | (ApprovalChain.mine_id.is_(None)),
            ApprovalChain.report_level == level,
        )
        .order_by(ApprovalChain.step_order)
        .all()
    )


def can_user_approve_entry(db: Session, user: User, entry: ShiftEntry) -> bool:
    if not user.role.can_approve:
        return False
    if user.mine_id is not None and user.mine_id != entry.mine_id:
        return False
    chain = get_approval_chain(db, entry.mine_id)
    if not chain:
        return user.role.rank > 2
    if entry.current_step >= len(chain):
        return False
    current_step_role = chain[entry.current_step].role_code
    return user.role_code == current_step_role


def submit_entry(db: Session, entry: ShiftEntry, actor: User) -> ShiftEntry:
    if entry.status not in ("DRAFT", "RETURNED"):
        raise ValueError(f"Cannot submit entry in status {entry.status}")
    if entry.foreman_id != actor.id:
        raise ValueError("Only the foreman who created the entry can submit it")

    entry.status = "SUBMITTED"
    entry.current_step = 0
    entry.updated_at = datetime.now(timezone.utc)

    db.add(ApprovalAction(
        subject_type="SHIFT_ENTRY",
        subject_id=entry.id,
        actor_id=actor.id,
        action="SUBMIT",
        ts=datetime.now(timezone.utc),
    ))
    append_audit(db, actor.id, "SUBMIT", "SHIFT_ENTRY", entry.id)
    return entry


def approve_entry(db: Session, entry: ShiftEntry, actor: User) -> ShiftEntry:
    if entry.status != "SUBMITTED":
        raise ValueError(f"Cannot approve entry in status {entry.status}")
    if not can_user_approve_entry(db, actor, entry):
        raise ValueError("User cannot approve this entry at the current step")

    chain = get_approval_chain(db, entry.mine_id)
    entry.current_step += 1

    if not chain or entry.current_step >= len(chain):
        entry.status = "APPROVED"
    else:
        entry.status = "SUBMITTED"

    entry.updated_at = datetime.now(timezone.utc)

    db.add(ApprovalAction(
        subject_type="SHIFT_ENTRY",
        subject_id=entry.id,
        actor_id=actor.id,
        action="APPROVE",
        ts=datetime.now(timezone.utc),
    ))
    append_audit(db, actor.id, "APPROVE", "SHIFT_ENTRY", entry.id)
    return entry


def return_entry(
    db: Session, entry: ShiftEntry, actor: User, comment: str
) -> ShiftEntry:
    if entry.status != "SUBMITTED":
        raise ValueError(f"Cannot return entry in status {entry.status}")
    if not comment.strip():
        raise ValueError("Return requires a comment")
    if not actor.role.can_approve:
        raise ValueError("User does not have approval permissions")

    entry.status = "RETURNED"
    entry.current_step = 0
    entry.updated_at = datetime.now(timezone.utc)

    db.add(ApprovalAction(
        subject_type="SHIFT_ENTRY",
        subject_id=entry.id,
        actor_id=actor.id,
        action="RETURN",
        comment=comment,
        ts=datetime.now(timezone.utc),
    ))
    append_audit(db, actor.id, "RETURN", "SHIFT_ENTRY", entry.id, {"comment": comment})
    return entry
