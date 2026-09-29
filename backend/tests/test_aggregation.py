from __future__ import annotations

from datetime import date

from app.db.models import (
    ApprovalChain,
    Bench,
    Mine,
    Role,
    Sector,
    ShiftEntry,
    Subsidiary,
    User,
)
from app.security import hash_password
from app.services.periods import month_clipped_weeks, week_for_date


def _seed(db):
    if db.query(User).filter(User.username == "agg_foreman").first():
        return
    if not db.query(Role).filter(Role.code == "FOREMAN").first():
        db.add(Role(code="FOREMAN", rank=1, label="Foreman", can_enter=True, can_approve=False))
    if not db.query(Role).filter(Role.code == "AE").first():
        db.add(Role(code="AE", rank=3, label="AE", can_enter=False, can_approve=True))
    db.flush()
    if not db.query(Sector).first():
        db.add(Sector(code="MINING"))
    if not db.query(Subsidiary).first():
        db.add(Subsidiary(code="NCL", name="NCL"))
    db.flush()
    sub = db.query(Subsidiary).first()
    sec = db.query(Sector).first()
    mine = db.query(Mine).filter(Mine.code == "AGG_MINE").first()
    if not mine:
        mine = Mine(code="AGG_MINE", name="Agg Mine", subsidiary_id=sub.id, sector_id=sec.id)
        db.add(mine)
        db.flush()
    bench = db.query(Bench).filter(Bench.code == "AGG_B").first()
    if not bench:
        bench = Bench(mine_id=mine.id, code="AGG_B", bench_type="SURFACE", name="Agg Bench")
        db.add(bench)
        db.flush()
    pw = hash_password("pass")
    db.add(User(username="agg_foreman", full_name="Agg Foreman", password_hash=pw, role_code="FOREMAN", mine_id=mine.id))
    db.add(User(username="agg_ae", full_name="Agg AE", password_hash=pw, role_code="AE", mine_id=mine.id))
    db.flush()
    if not db.query(ApprovalChain).filter(ApprovalChain.mine_id == mine.id).first():
        db.add(ApprovalChain(mine_id=mine.id, report_level="DAILY", step_order=0, role_code="AE"))
    db.commit()
    return mine, bench


def _login(client, username):
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": "pass"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_approved_entries(client, mine_id, bench_id, work_date, foreman_token, ae_token):
    """Create 3 shift entries (A, B, C) and approve them all."""
    for shift in ["A", "B", "C"]:
        resp = client.post("/api/v1/shift-entries", json={
            "mine_id": mine_id,
            "bench_id": bench_id,
            "work_date": work_date,
            "shift_code": shift,
            "planned_min": 480,
            "workers_present": 10,
            "production_milli_t": 5000,
            "ob_milli_m3": 15000,
            "downtime_events": [],
        }, headers=_auth(foreman_token))
        assert resp.status_code == 201, resp.text
        entry_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/shift-entries/{entry_id}/submit",
            headers=_auth(foreman_token),
        )
        assert resp.status_code == 200

        resp = client.post(
            f"/api/v1/shift-entries/{entry_id}/approve",
            headers=_auth(ae_token),
        )
        assert resp.status_code == 200


def test_month_clipped_weeks():
    weeks = month_clipped_weeks(2026, 9)
    assert len(weeks) == 5
    assert weeks[0] == (date(2026, 9, 1), date(2026, 9, 7))
    assert weeks[1] == (date(2026, 9, 8), date(2026, 9, 14))
    assert weeks[2] == (date(2026, 9, 15), date(2026, 9, 21))
    assert weeks[3] == (date(2026, 9, 22), date(2026, 9, 28))
    assert weeks[4] == (date(2026, 9, 29), date(2026, 9, 30))

    feb_weeks = month_clipped_weeks(2026, 2)
    assert len(feb_weeks) == 4
    assert feb_weeks[-1] == (date(2026, 2, 22), date(2026, 2, 28))


def test_week_for_date():
    start, end = week_for_date(date(2026, 9, 10))
    assert start == date(2026, 9, 8)
    assert end == date(2026, 9, 14)


def test_generate_daily_report(client):
    from app.db.session import get_session_factory

    session = get_session_factory()()
    result = _seed(session)
    mine = session.query(Mine).filter(Mine.code == "AGG_MINE").first()
    bench = session.query(Bench).filter(Bench.code == "AGG_B").first()
    session.close()

    foreman_token = _login(client, "agg_foreman")
    ae_token = _login(client, "agg_ae")

    _create_approved_entries(
        client, mine.id, bench.id, "2026-09-01",
        foreman_token, ae_token,
    )

    resp = client.post("/api/v1/reports/generate", json={
        "level": "DAILY",
        "mine_id": mine.id,
        "bench_id": bench.id,
        "period_start": "2026-09-01",
        "period_end": "2026-09-01",
    }, headers=_auth(foreman_token))
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["level"] == "DAILY"
    assert data["expected_children"] == 3
    assert data["present_children"] == 3

    metrics = {m["metric_code"]: m["value_int"] for m in data["metrics"]}
    assert metrics["production_milli_t"] == 15000
    assert metrics["ob_milli_m3"] == 45000
    assert metrics["planned_min"] == 1440
    assert metrics["operating_min"] == 1440
    assert metrics["workers_present"] == 30

    assert len(data["lineage_edges"]) == 3
    for edge in data["lineage_edges"]:
        assert edge["child_kind"] == "SHIFT_ENTRY"


def test_reconciliation(client):
    foreman_token = _login(client, "agg_foreman")

    from app.db.session import get_session_factory

    session = get_session_factory()()
    mine = session.query(Mine).filter(Mine.code == "AGG_MINE").first()
    bench = session.query(Bench).filter(Bench.code == "AGG_B").first()
    session.close()

    resp = client.get("/api/v1/reports", params={
        "mine_id": mine.id,
        "bench_id": bench.id,
        "level": "DAILY",
    }, headers=_auth(foreman_token))
    assert resp.status_code == 200
    reports = resp.json()
    assert len(reports) >= 1
    report_id = reports[0]["id"]

    resp = client.get(
        f"/api/v1/reports/{report_id}/reconcile",
        headers=_auth(foreman_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["issues"] == []


def test_lineage_detail(client):
    foreman_token = _login(client, "agg_foreman")

    from app.db.session import get_session_factory

    session = get_session_factory()()
    mine = session.query(Mine).filter(Mine.code == "AGG_MINE").first()
    bench = session.query(Bench).filter(Bench.code == "AGG_B").first()
    session.close()

    resp = client.get("/api/v1/reports", params={
        "mine_id": mine.id,
        "bench_id": bench.id,
        "level": "DAILY",
    }, headers=_auth(foreman_token))
    report_id = resp.json()[0]["id"]

    resp = client.get(
        f"/api/v1/reports/{report_id}/lineage",
        headers=_auth(foreman_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["contributions"]) > 0
    assert len(data["edges"]) == 3

    prod_contribs = [
        c for c in data["contributions"] if c["metric_code"] == "production_milli_t"
    ]
    assert len(prod_contribs) == 3
    assert sum(c["contributed_value_int"] for c in prod_contribs) == 15000


def test_generate_weekly_from_dailies(client):
    from app.db.session import get_session_factory

    session = get_session_factory()()
    mine = session.query(Mine).filter(Mine.code == "AGG_MINE").first()
    bench = session.query(Bench).filter(Bench.code == "AGG_B").first()
    session.close()

    foreman_token = _login(client, "agg_foreman")
    ae_token = _login(client, "agg_ae")

    for day in range(2, 8):
        _create_approved_entries(
            client, mine.id, bench.id, f"2026-09-{day:02d}",
            foreman_token, ae_token,
        )
        client.post("/api/v1/reports/generate", json={
            "level": "DAILY",
            "mine_id": mine.id,
            "bench_id": bench.id,
            "period_start": f"2026-09-{day:02d}",
            "period_end": f"2026-09-{day:02d}",
        }, headers=_auth(foreman_token))

    resp = client.post("/api/v1/reports/generate", json={
        "level": "WEEKLY",
        "mine_id": mine.id,
        "bench_id": bench.id,
        "period_start": "2026-09-01",
        "period_end": "2026-09-07",
    }, headers=_auth(foreman_token))
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["level"] == "WEEKLY"
    assert data["expected_children"] == 7
    assert data["present_children"] == 7

    metrics = {m["metric_code"]: m["value_int"] for m in data["metrics"]}
    assert metrics["production_milli_t"] == 15000 * 7
    assert metrics["planned_min"] == 1440 * 7

    for edge in data["lineage_edges"]:
        assert edge["child_kind"] == "REPORT"
