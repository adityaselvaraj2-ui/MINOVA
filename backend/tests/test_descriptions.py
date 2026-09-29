from __future__ import annotations

from app.services.numberguard import build_allowed_set, extract_numbers, guard_check


def test_extract_numbers():
    text = "Production was 15.000 tonnes with 45.000 m3 overburden."
    nums = extract_numbers(text)
    assert "15.000" in nums
    assert "45.000" in nums


def test_extract_ignores_small():
    text = "There were 3 shifts and 2 benches producing 500.000 tonnes."
    nums = extract_numbers(text)
    assert "500.000" in nums
    assert "3" not in nums
    assert "2" not in nums


def test_build_allowed_set():
    fact_sheet = {
        "production_t": "15.000",
        "overburden_m3": "45.000",
        "planned_min": 1440,
        "operating_min": 1440,
        "availability_pct": "100.00",
    }
    allowed = build_allowed_set(fact_sheet)
    assert "15.000" in allowed
    assert "45.000" in allowed
    assert "1440" in allowed
    assert "100.00" in allowed


def test_guard_pass():
    text = "Production: 15.000 tonnes, OB: 45.000 m3, availability: 100.00%"
    fact_sheet = {
        "production_t": "15.000",
        "overburden_m3": "45.000",
        "availability_pct": "100.00",
    }
    result = guard_check(text, fact_sheet)
    assert result["result"] == "PASS"


def test_guard_fail():
    text = "Production: 99.999 tonnes"
    fact_sheet = {"production_t": "15.000"}
    result = guard_check(text, fact_sheet)
    assert result["result"] == "FAIL"
    assert "99.999" in result["violations"]


def test_template_fallback_via_api(client):
    from app.db.models import (
        ApprovalChain,
        Bench,
        Mine,
        Role,
        Sector,
        Subsidiary,
        User,
    )
    from app.db.session import get_session_factory
    from app.security import hash_password

    session = get_session_factory()()
    if not session.query(User).filter(User.username == "desc_foreman").first():
        if not session.query(Role).filter(Role.code == "FOREMAN").first():
            session.add(Role(code="FOREMAN", rank=1, label="Foreman", can_enter=True, can_approve=False))
        if not session.query(Role).filter(Role.code == "AE").first():
            session.add(Role(code="AE", rank=3, label="AE", can_enter=False, can_approve=True))
        session.flush()
        if not session.query(Sector).first():
            session.add(Sector(code="MINING"))
        if not session.query(Subsidiary).first():
            session.add(Subsidiary(code="NCL", name="NCL"))
        session.flush()
        sub = session.query(Subsidiary).first()
        sec = session.query(Sector).first()
        mine = session.query(Mine).filter(Mine.code == "DESC_MINE").first()
        if not mine:
            mine = Mine(code="DESC_MINE", name="Desc Mine", subsidiary_id=sub.id, sector_id=sec.id)
            session.add(mine)
            session.flush()
        bench = session.query(Bench).filter(Bench.code == "DESC_B").first()
        if not bench:
            bench = Bench(mine_id=mine.id, code="DESC_B", bench_type="SURFACE", name="Desc Bench")
            session.add(bench)
            session.flush()
        pw = hash_password("pass")
        session.add(User(username="desc_foreman", full_name="Desc F", password_hash=pw, role_code="FOREMAN", mine_id=mine.id))
        session.add(User(username="desc_ae", full_name="Desc AE", password_hash=pw, role_code="AE", mine_id=mine.id))
        session.flush()
        if not session.query(ApprovalChain).filter(ApprovalChain.mine_id == mine.id).first():
            session.add(ApprovalChain(mine_id=mine.id, report_level="DAILY", step_order=0, role_code="AE"))
        session.commit()

    mine = session.query(Mine).filter(Mine.code == "DESC_MINE").first()
    bench = session.query(Bench).filter(Bench.code == "DESC_B").first()
    session.close()

    def _login(u):
        r = client.post("/api/v1/auth/login", json={"username": u, "password": "pass"})
        assert r.status_code == 200
        return r.json()["access_token"]

    ft = _login("desc_foreman")
    at = _login("desc_ae")
    auth_f = {"Authorization": f"Bearer {ft}"}
    auth_a = {"Authorization": f"Bearer {at}"}

    for shift in ["A", "B", "C"]:
        r = client.post("/api/v1/shift-entries", json={
            "mine_id": mine.id, "bench_id": bench.id,
            "work_date": "2026-08-01", "shift_code": shift,
            "planned_min": 480, "workers_present": 10,
            "production_milli_t": 4000, "ob_milli_m3": 12000,
            "downtime_events": [],
        }, headers=auth_f)
        eid = r.json()["id"]
        client.post(f"/api/v1/shift-entries/{eid}/submit", headers=auth_f)
        client.post(f"/api/v1/shift-entries/{eid}/approve", headers=auth_a)

    r = client.post("/api/v1/reports/generate", json={
        "level": "DAILY", "mine_id": mine.id, "bench_id": bench.id,
        "period_start": "2026-08-01", "period_end": "2026-08-01",
    }, headers=auth_f)
    assert r.status_code == 200
    report_id = r.json()["id"]

    r = client.post(f"/api/v1/descriptions/{report_id}/generate", headers=auth_f)
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "TEMPLATE_FALLBACK"
    assert "12.000" in data["text_recorded"]
    assert data["guard_result"] == "TEMPLATE"

    r = client.get(f"/api/v1/descriptions/{report_id}", headers=auth_f)
    assert r.status_code == 200
    assert r.json()["source"] == "TEMPLATE_FALLBACK"
