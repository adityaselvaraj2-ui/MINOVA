"""Seed the database with SYNTHETIC / ILLUSTRATIVE demo data.

ALL DATA IS SYNTHETIC AND NOT VERIFIED. For demonstration purposes only.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import settings
from app.db.models import (
    ApprovalAction,
    ApprovalChain,
    AuditLog,
    Bench,
    DowntimeEvent,
    Equipment,
    Mine,
    Role,
    Sector,
    ShiftEntry,
    Subsidiary,
    Target,
    User,
)
from app.db.session import Base, get_engine, init_db
from app.security import hash_password

settings.ensure_dirs()
init_db()
engine = get_engine()

SEED = 42
rng = random.Random(SEED)


def _audit_hash(prev: str | None, record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, default=str)
    data = (prev or "") + payload
    return hashlib.sha256(data.encode()).hexdigest()


def seed():
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        if db.query(Subsidiary).count() > 0:
            print("Database already seeded. Skipping.")
            return

        # --- Sectors ---
        sectors = {}
        for code in ("MINING", "POWER", "WATER", "BRICKS", "OTHER"):
            s = Sector(code=code)
            db.add(s)
            db.flush()
            sectors[code] = s

        # --- Subsidiaries (CIL) ---
        subs_data = [
            ("ECL", "Eastern Coalfields Limited"),
            ("BCCL", "Bharat Coking Coal Limited"),
            ("CCL", "Central Coalfields Limited"),
            ("NCL", "Northern Coalfields Limited"),
            ("WCL", "Western Coalfields Limited"),
            ("SECL", "South Eastern Coalfields Limited"),
            ("MCL", "Mahanadi Coalfields Limited"),
            ("NEC", "North Eastern Coalfields"),
        ]
        subs = {}
        for code, name in subs_data:
            sub = Subsidiary(code=code, name=name)
            db.add(sub)
            db.flush()
            subs[code] = sub

        # --- Roles (UNVERIFIED hierarchy from field notes) ---
        roles_data = [
            ("FOREMAN", 1, "Foreman", True, False),
            ("EXEC_SUPERVISOR", 2, "Executive Supervisor", True, False),
            ("AE", 3, "Assistant Engineer", False, True),
            ("EE", 4, "Executive Engineer", False, True),
            ("DCM", 5, "Deputy Chief Manager", False, True),
            ("ACM", 6, "Assistant Chief Manager", False, True),
            ("CM", 7, "Chief Manager", False, True),
            ("DGM", 8, "Deputy General Manager", False, True),
            ("GM", 9, "General Manager", False, True),
            ("CGM", 10, "Chief General Manager", False, True),
            ("DIRECTOR", 11, "Director", False, True),
            ("CMD", 12, "Chairman & Managing Director", False, True),
            ("ADMIN", 99, "System Administrator", False, False),
        ]
        roles = {}
        for code, rank, label, can_enter, can_approve in roles_data:
            r = Role(code=code, rank=rank, label=label, can_enter=can_enter, can_approve=can_approve)
            db.add(r)
            roles[code] = r

        db.flush()

        # --- Mines (3 illustrative mines under NCL, from field notes) ---
        mines_data = [
            ("MINE1", "Mine 1 - Jayant", "NCL", 2_000_000),
            ("MINE1A", "Mine 1A - Dudhichua", "NCL", 7_500_000),
            ("MINE2", "Mine 2 - Nigahi", "NCL", 15_000_000),
        ]
        mines = {}
        for code, name, sub_code, annual_target_t in mines_data:
            m = Mine(
                code=code,
                name=name,
                subsidiary_id=subs[sub_code].id,
                sector_id=sectors["MINING"].id,
            )
            db.add(m)
            db.flush()
            mines[code] = (m, annual_target_t)

        # --- Benches (4 per mine) ---
        bench_types = ["SURFACE", "TOP", "MIDDLE", "BOTTOM"]
        benches = {}
        for mine_code, (mine, _) in mines.items():
            for bt in bench_types:
                b = Bench(
                    mine_id=mine.id,
                    code=f"{mine_code}_{bt[:3]}",
                    bench_type=bt,
                    name=f"{mine.name} - {bt.title()} Bench",
                )
                db.add(b)
                db.flush()
                benches[(mine_code, bt)] = b

        # --- Equipment (3 per mine) ---
        equip_types = [
            ("DRAGLINE", "Dragline"),
            ("SHOVEL", "Electric Shovel"),
            ("DUMPER", "Rear Dumper"),
        ]
        equipment = {}
        for mine_code, (mine, _) in mines.items():
            for i, (etype, ename) in enumerate(equip_types):
                e = Equipment(
                    mine_id=mine.id,
                    code=f"{mine_code}_EQ{i+1}",
                    type=etype,
                    name=f"{ename} - {mine.name}",
                )
                db.add(e)
                db.flush()
                equipment[(mine_code, i)] = e

        # --- Users (one per role per mine + admin) ---
        default_pw = hash_password("demo123")
        users = {}

        admin = User(
            username="admin",
            full_name="System Administrator",
            password_hash=default_pw,
            role_code="ADMIN",
            department="IT",
        )
        db.add(admin)
        db.flush()
        users["admin"] = admin

        user_names = {
            "FOREMAN": [("ramesh", "Ramesh Kumar"), ("suresh", "Suresh Patel"), ("mahesh", "Mahesh Singh")],
            "EXEC_SUPERVISOR": [("priya", "Priya Sharma"), ("anita", "Anita Devi"), ("ravi", "Ravi Tiwari")],
            "AE": [("amit", "Amit Verma"), ("deepak", "Deepak Gupta"), ("rohit", "Rohit Yadav")],
            "EE": [("sanjay", "Sanjay Mishra"), ("vijay", "Vijay Kumar"), ("ajay", "Ajay Pandey")],
            "CM": [("rajesh", "Rajesh Srivastava"), ("dinesh", "Dinesh Mohan"), ("ganesh", "Ganesh Rao")],
            "GM": [("arun", "Arun Prakash"), ("varun", "Varun Sharma"), ("tarun", "Tarun Mehta")],
        }

        for role_code, name_list in user_names.items():
            for i, (uname, fullname) in enumerate(name_list):
                mine_code = list(mines.keys())[i]
                mine_obj = mines[mine_code][0]
                u = User(
                    username=uname,
                    full_name=fullname,
                    password_hash=default_pw,
                    role_code=role_code,
                    mine_id=mine_obj.id,
                    department="Mining",
                )
                db.add(u)
                db.flush()
                users[(role_code, mine_code)] = u

        # --- Approval chains ---
        for mine_code, (mine, _) in mines.items():
            for level in ("DAILY", "WEEKLY", "MONTHLY"):
                chain = [("AE", 1), ("EE", 2)]
                if level in ("WEEKLY", "MONTHLY"):
                    chain.append(("CM", 3))
                for rc, step in chain:
                    db.add(ApprovalChain(
                        mine_id=mine.id,
                        report_level=level,
                        step_order=step,
                        role_code=rc,
                    ))

        # --- Targets (annual, split equally by month, illustrative) ---
        fy_start = date(2025, 10, 1)
        fy_end = date(2026, 9, 30)
        for mine_code, (mine, annual_t) in mines.items():
            monthly_t = annual_t // 12
            ob_annual = annual_t * 4  # 1:4 stripping ratio
            monthly_ob = ob_annual // 12

            db.add(Target(
                mine_id=mine.id, period_level="ANNUAL",
                period_start=fy_start, period_end=fy_end,
                metric_code="PRODUCTION_T", value_int=annual_t * 1000, unit="milli_t",
                source_note="SYNTHETIC - from field notes",
            ))
            db.add(Target(
                mine_id=mine.id, period_level="ANNUAL",
                period_start=fy_start, period_end=fy_end,
                metric_code="OB_M3", value_int=ob_annual * 1000, unit="milli_m3",
                source_note="SYNTHETIC - 1:4 stripping ratio",
            ))

            cur = fy_start
            while cur < fy_end:
                m_end = (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                if m_end > fy_end:
                    m_end = fy_end
                db.add(Target(
                    mine_id=mine.id, period_level="MONTHLY",
                    period_start=cur, period_end=m_end,
                    metric_code="PRODUCTION_T", value_int=monthly_t * 1000, unit="milli_t",
                    source_note="SYNTHETIC - equal monthly split",
                ))
                cur = m_end + timedelta(days=1)

        db.flush()

        # --- Shift entries (12 months, 3 shifts/day, 4 benches, 3 mines) ---
        print("Generating shift entries (this may take a moment)...")
        prev_audit_hash = None
        entry_count = 0
        statuses_pool = ["APPROVED"] * 85 + ["DRAFT"] * 5 + ["SUBMITTED"] * 5 + ["RETURNED"] * 5

        d = fy_start
        while d <= min(fy_end, date(2026, 9, 28)):
            for mine_code, (mine, annual_t) in mines.items():
                daily_target_t = annual_t / 365
                foreman = users.get(("FOREMAN", mine_code))
                if foreman is None:
                    continue

                for bt in bench_types:
                    bench = benches[(mine_code, bt)]
                    bench_share = {"SURFACE": 0.15, "TOP": 0.30, "MIDDLE": 0.35, "BOTTOM": 0.20}[bt]

                    for shift_code in ("A", "B", "C"):
                        shift_share = {"A": 0.40, "B": 0.35, "C": 0.25}[shift_code]
                        base_prod = daily_target_t * bench_share * shift_share

                        is_rainy = d.month in (6, 7, 8, 9) and rng.random() < 0.3
                        has_breakdown = rng.random() < 0.08
                        has_fire = rng.random() < 0.003

                        prod_factor = rng.gauss(1.0, 0.15)
                        if is_rainy:
                            prod_factor *= 0.6
                        if has_breakdown:
                            prod_factor *= 0.5
                        if has_fire:
                            prod_factor *= 0.1

                        prod_t = max(0, base_prod * prod_factor)
                        ob_m3 = prod_t * rng.gauss(4.0, 0.5)

                        planned_min = 480
                        stoppage = 0
                        weather_code = None
                        rainfall = None

                        if is_rainy:
                            stoppage += rng.randint(60, 240)
                            weather_code = "RAIN"
                            rainfall = rng.randint(50, 300)
                        if has_breakdown:
                            stoppage += rng.randint(30, 180)
                        if has_fire:
                            stoppage += rng.randint(120, 420)

                        stoppage = min(stoppage, planned_min)
                        operating = planned_min - stoppage
                        workers = rng.randint(8, 25)

                        entry_status = rng.choice(statuses_pool)
                        entry_uuid = str(uuid.UUID(int=rng.getrandbits(128), version=4))

                        se = ShiftEntry(
                            uuid=entry_uuid,
                            mine_id=mine.id,
                            bench_id=bench.id,
                            work_date=d,
                            shift_code=shift_code,
                            foreman_id=foreman.id,
                            planned_min=planned_min,
                            workers_present=workers,
                            production_milli_t=int(prod_t * 1000),
                            ob_milli_m3=int(ob_m3 * 1000),
                            stoppage_min=stoppage,
                            operating_min=operating,
                            weather_code=weather_code,
                            rainfall_mm_x10=rainfall,
                            status=entry_status,
                            version=1,
                            current_step=2 if entry_status == "APPROVED" else 0,
                            created_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                            updated_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                        )
                        db.add(se)
                        db.flush()

                        # Downtime events
                        if is_rainy:
                            dt_start = rng.randint(0, 300)
                            dt_dur = rng.randint(60, min(180, stoppage))
                            db.add(DowntimeEvent(
                                shift_entry_id=se.id,
                                category="WEATHER",
                                start_min=dt_start,
                                end_min=dt_start + dt_dur,
                                duration_min=dt_dur,
                                cause_text="Heavy rainfall, operations suspended",
                            ))
                        if has_breakdown:
                            eq = equipment.get((mine_code, rng.randint(0, 2)))
                            dt_start = rng.randint(0, 300)
                            dt_dur = rng.randint(30, 120)
                            db.add(DowntimeEvent(
                                shift_entry_id=se.id,
                                equipment_id=eq.id if eq else None,
                                category="EQUIPMENT_FAILURE",
                                start_min=dt_start,
                                end_min=dt_start + dt_dur,
                                duration_min=dt_dur,
                                cause_text="Hydraulic system failure" if rng.random() > 0.5 else "Belt conveyor jam",
                            ))
                        if has_fire:
                            db.add(DowntimeEvent(
                                shift_entry_id=se.id,
                                category="FIRE_INCIDENT",
                                start_min=0,
                                end_min=min(420, stoppage),
                                duration_min=min(420, stoppage),
                                cause_text="Spontaneous coal combustion detected in bench face",
                            ))

                        # Approval actions for APPROVED entries
                        if entry_status == "APPROVED":
                            db.add(ApprovalAction(
                                subject_type="SHIFT_ENTRY",
                                subject_id=se.id,
                                actor_id=foreman.id,
                                action="SUBMIT",
                                ts=datetime(d.year, d.month, d.day, 8, 0, tzinfo=timezone.utc),
                            ))
                            ae = users.get(("AE", mine_code))
                            if ae:
                                db.add(ApprovalAction(
                                    subject_type="SHIFT_ENTRY",
                                    subject_id=se.id,
                                    actor_id=ae.id,
                                    action="APPROVE",
                                    ts=datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc),
                                ))

                            record = {
                                "action": "APPROVE", "subject_type": "SHIFT_ENTRY",
                                "subject_id": se.id, "actor_id": ae.id if ae else foreman.id,
                            }
                            h = _audit_hash(prev_audit_hash, record)
                            db.add(AuditLog(
                                actor_id=ae.id if ae else foreman.id,
                                action="APPROVE",
                                subject_type="SHIFT_ENTRY",
                                subject_id=se.id,
                                payload_json=json.dumps(record, default=str),
                                prev_hash=prev_audit_hash,
                                hash=h,
                            ))
                            prev_audit_hash = h

                        entry_count += 1

            # commit every 30 days to avoid huge transactions
            if d.day == 28 or d == min(fy_end, date(2026, 9, 28)):
                db.commit()
                print(f"  Seeded through {d} ({entry_count} entries so far)")

            d += timedelta(days=1)

        db.commit()
        print(f"\nSeed complete: {entry_count} shift entries across 3 mines.")
        print("Default login: any username with password 'demo123'")
        print("Examples: admin, ramesh (foreman), amit (AE), sanjay (EE)")


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    seed()
