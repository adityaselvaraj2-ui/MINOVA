from __future__ import annotations

from app.db.models import (
    ApprovalChain,
    Bench,
    Mine,
    Role,
    Sector,
    Subsidiary,
    User,
)
from app.security import hash_password


def _ensure_data(db):
    if db.query(User).filter(User.username == "foreman1").first():
        return

    if not db.query(Role).filter(Role.code == "FOREMAN").first():
        db.add(Role(code="FOREMAN", rank=1, label="Foreman", can_enter=True, can_approve=False))
    if not db.query(Role).filter(Role.code == "AE").first():
        db.add(Role(code="AE", rank=3, label="Assistant Engineer", can_enter=False, can_approve=True))
    db.flush()

    if not db.query(Sector).first():
        db.add(Sector(code="MINING"))
    if not db.query(Subsidiary).first():
        db.add(Subsidiary(code="NCL", name="NCL"))
    db.flush()

    sub = db.query(Subsidiary).first()
    sec = db.query(Sector).first()

    mine = db.query(Mine).filter(Mine.code == "TEST_MINE").first()
    if not mine:
        mine = Mine(code="TEST_MINE", name="Test Mine", subsidiary_id=sub.id, sector_id=sec.id)
        db.add(mine)
        db.flush()

    bench = db.query(Bench).filter(Bench.code == "TEST_B").first()
    if not bench:
        bench = Bench(mine_id=mine.id, code="TEST_B", bench_type="SURFACE", name="Test Bench")
        db.add(bench)
        db.flush()

    pw = hash_password("pass")
    db.add(User(
        username="foreman1", full_name="Foreman 1", password_hash=pw,
        role_code="FOREMAN", mine_id=mine.id,
    ))
    db.add(User(
        username="ae1", full_name="AE 1", password_hash=pw,
        role_code="AE", mine_id=mine.id,
    ))
    db.flush()

    if not db.query(ApprovalChain).filter(ApprovalChain.mine_id == mine.id).first():
        db.add(ApprovalChain(
            mine_id=mine.id, report_level="DAILY", step_order=0, role_code="AE",
        ))
    db.commit()


def _login(client, username):
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": "pass"})
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_shift_entry(client):
    from app.db.session import get_session_factory

    session = get_session_factory()()
    _ensure_data(session)

    from app.db.models import Bench, Mine

    mine = session.query(Mine).filter(Mine.code == "TEST_MINE").first()
    bench = session.query(Bench).filter(Bench.code == "TEST_B").first()
    session.close()

    token = _login(client, "foreman1")
    resp = client.post("/api/v1/shift-entries", json={
        "mine_id": mine.id,
        "bench_id": bench.id,
        "work_date": "2026-09-01",
        "shift_code": "A",
        "planned_min": 480,
        "workers_present": 15,
        "production_milli_t": 5000,
        "ob_milli_m3": 20000,
        "downtime_events": [],
    }, headers=_auth(token))
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["status"] == "DRAFT"
    assert data["operating_min"] == 480


def test_submit_approve_workflow(client):
    from app.db.session import get_session_factory

    session = get_session_factory()()
    _ensure_data(session)
    from app.db.models import Bench, Mine

    mine = session.query(Mine).filter(Mine.code == "TEST_MINE").first()
    bench = session.query(Bench).filter(Bench.code == "TEST_B").first()
    session.close()

    foreman_token = _login(client, "foreman1")
    ae_token = _login(client, "ae1")

    resp = client.post("/api/v1/shift-entries", json={
        "mine_id": mine.id,
        "bench_id": bench.id,
        "work_date": "2026-09-02",
        "shift_code": "B",
        "planned_min": 480,
        "workers_present": 10,
        "production_milli_t": 3000,
        "ob_milli_m3": 12000,
        "downtime_events": [{
            "category": "WEATHER",
            "start_min": 60,
            "end_min": 180,
            "cause_text": "Rain",
        }],
    }, headers=_auth(foreman_token))
    assert resp.status_code == 201
    entry_id = resp.json()["id"]
    assert resp.json()["stoppage_min"] == 120
    assert resp.json()["operating_min"] == 360

    resp = client.post(f"/api/v1/shift-entries/{entry_id}/submit", headers=_auth(foreman_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUBMITTED"

    resp = client.post(f"/api/v1/shift-entries/{entry_id}/approve", headers=_auth(ae_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"


def test_return_requires_comment(client):
    from app.db.session import get_session_factory

    session = get_session_factory()()
    _ensure_data(session)
    from app.db.models import Bench, Mine

    mine = session.query(Mine).filter(Mine.code == "TEST_MINE").first()
    bench = session.query(Bench).filter(Bench.code == "TEST_B").first()
    session.close()

    foreman_token = _login(client, "foreman1")
    ae_token = _login(client, "ae1")

    resp = client.post("/api/v1/shift-entries", json={
        "mine_id": mine.id,
        "bench_id": bench.id,
        "work_date": "2026-09-03",
        "shift_code": "C",
        "planned_min": 480,
        "workers_present": 8,
        "production_milli_t": 2000,
        "ob_milli_m3": 8000,
    }, headers=_auth(foreman_token))
    entry_id = resp.json()["id"]

    client.post(f"/api/v1/shift-entries/{entry_id}/submit", headers=_auth(foreman_token))

    resp = client.post(
        f"/api/v1/shift-entries/{entry_id}/return",
        json={"comment": ""},
        headers=_auth(ae_token),
    )
    assert resp.status_code == 400

    resp = client.post(
        f"/api/v1/shift-entries/{entry_id}/return",
        json={"comment": "Production figures seem too low"},
        headers=_auth(ae_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "RETURNED"


def test_audit_chain_valid(client):
    token = _login(client, "foreman1")
    resp = client.get("/api/v1/audit/verify", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True


def test_validation_rejects_bad_data(client):
    token = _login(client, "foreman1")
    resp = client.post("/api/v1/shift-entries", json={
        "mine_id": 999,
        "bench_id": 999,
        "work_date": "2026-09-05",
        "shift_code": "A",
        "planned_min": 480,
        "workers_present": 10,
        "production_milli_t": 1000,
        "ob_milli_m3": 4000,
    }, headers=_auth(token))
    assert resp.status_code == 422
