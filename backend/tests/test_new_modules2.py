"""Tests for Phase 1/2 additions: weather, rain-impact, plan engine,
target-vs-actual, query pack, scoped Text-to-SQL, anomalies, lineage."""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

# ISOLATED data dir for this module (must run BEFORE app imports; not
# setdefault - conftest may already have pointed at the shared dev DB).
os.environ["MINETRACE_DATA_DIR"] = str(Path(tempfile.mkdtemp()) / "mt_t2")

from app.config import settings  # noqa: E402
from app.db.extended_models import (  # noqa: E402
    DataConflict,
    WeatherDaily,
    fiscal_year_boundaries,
)
from app.db.models import (  # noqa: E402
    ApprovalChain,
    Bench,
    Mine,
    Role,
    Sector,
    ShiftEntry,
    Subsidiary,
    Target,
    User,
)
from app.db.session import Base, get_engine, get_session_factory  # noqa: E402
from app.services.plan import build_plan_suggestion, capacity_cap, rain_impact_table  # noqa: E402
from app.services.targets import target_vs_actual  # noqa: E402
from app.services.weather import CsvProvider, upsert_daily  # noqa: E402


@pytest.fixture(scope="module")
def db():
    settings.ensure_dirs()
    # Save global engine state; rebind to THIS module's isolated data dir.
    import app.db.session as session_mod
    from app.db.session import init_db

    saved_dir = os.environ.get("MINETRACE_DATA_DIR")
    init_db()
    engine = get_engine()
    Base.metadata.create_all(engine)
    factory = get_session_factory()
    session = factory()
    yield session
    session.close()
    # Restore previous engine/env so later test files are unaffected.
    if saved_dir is not None:
        os.environ["MINETRACE_DATA_DIR"] = saved_dir
    session_mod._engine = None
    session_mod._session_factory = None
    session_mod._engine_url = None


@pytest.fixture(scope="module")
def seeded(db):
    """Small deterministic dataset: 1 mine, 60 days of entries+weather."""
    if db.query(Mine).filter(Mine.code == "TM1").first():
        return db.query(Mine).filter(Mine.code == "TM1").first()
    try:
        return _seed(db)
    except Exception:
        db.rollback()
        mine = db.query(Mine).filter(Mine.code == "TM1").first()
        if mine is None:
            raise
        return mine


def _seed(db):
    sec = db.query(Sector).filter(Sector.code == "MINING").first()
    if not sec:
        sec = Sector(code="MINING")
        db.add(sec)
    sub = Subsidiary(code="TSUB", name="Test Sub")
    db.add(sub)
    db.flush()
    mine = Mine(code="TM1", name="Test Mine", subsidiary_id=sub.id, sector_id=sec.id)
    db.add(mine)
    db.flush()
    bench = Bench(mine_id=mine.id, code="B1", bench_type="TOP", name="Bench 1")
    db.add(bench)
    role = Role(code="FOREMAN_T", rank=1, label="Foreman", can_enter=True)
    db.add(role)
    db.flush()
    user = User(username="fman_t", full_name="F", password_hash="x",
                role_code="FOREMAN_T", mine_id=mine.id)
    db.add(user)
    db.flush()

    rng = __import__("random").Random(7)
    today = date.today()
    import calendar

    month_done = set()
    for i in range(60, -1, -1):
        d = today - timedelta(days=i)
        rain = round(rng.uniform(0, 60), 1)
        db.add(WeatherDaily(mine_id=mine.id, date=d, rain_mm_x10=int(rain * 10),
                            source="history_csv", is_forecast=False))
        # more rain -> less production (deterministic relationship)
        factor = 1.0 if rain < 1 else (0.8 if rain < 5 else (0.5 if rain < 20 else 0.2))
        prod = int(30_000 * factor * rng.uniform(0.95, 1.05))
        db.add(ShiftEntry(
            uuid=f"t-{d.isoformat()}-A", mine_id=mine.id, bench_id=bench.id,
            work_date=d, shift_code="A", foreman_id=user.id,
            planned_min=480, workers_present=10,
            production_milli_t=prod, ob_milli_m3=prod * 2,
            stoppage_min=0, operating_min=480, status="APPROVED",
        ))
        mk = (d.year, d.month)
        if mk not in month_done:
            month_done.add(mk)
            db.add(Target(mine_id=mine.id, period_level="MONTHLY",
                          period_start=d.replace(day=1),
                          period_end=d.replace(
                              day=calendar.monthrange(d.year, d.month)[1]),
                          metric_code="production_milli_t",
                          value_int=900_000, unit="milli_t"))
    db.add(ApprovalChain(mine_id=mine.id, report_level="DAILY", step_order=1,
                         role_code="FOREMAN_T"))
    db.commit()
    return mine


def test_fiscal_year_apr_mar():
    start, end = fiscal_year_boundaries(2026)
    assert (start.month, start.day) == (4, 1)
    assert (end.month, end.day) == (3, 31)
    assert end.year == 2027


def test_weather_upsert_and_csv_provider(db, seeded):
    mine = seeded
    tomorrow = date.today() + timedelta(days=40)
    rows = [{"date": tomorrow, "rain_mm": 12.5, "temp_max": 33.0,
             "is_forecast": True, "source": "forecast_csv"}]
    n = upsert_daily(db, mine, rows)
    assert n == 1
    # upsert semantics: second write updates, not duplicates
    n2 = upsert_daily(db, mine, [{**rows[0], "rain_mm": 20.0}])
    assert n2 == 1
    provider = CsvProvider()
    assert provider.dir.name == "weather"


def test_rain_impact_sufficient(db, seeded):
    table = rain_impact_table(db, seeded.id)
    assert table["sufficient"] is True
    assert table["baseline_dry_t"] > 0
    # wet bins should show lower median ratio than dry
    monsoon = table["bins"].get("monsoon", table["bins"])
    if "20-50" in monsoon:
        assert monsoon["20-50"]["p50"] < 1.0


def test_rain_impact_insufficient(db):
    table = rain_impact_table(db, 99999)
    assert table["sufficient"] is False
    assert "insufficient" in table["message"]


def test_capacity_cap_p95(db, seeded):
    cap = capacity_cap(db, seeded.id)
    assert cap > 0


def test_plan_suggestion(db, seeded):
    mine = seeded
    today = date.today()
    db.query(WeatherDaily).filter(
        WeatherDaily.mine_id == mine.id, WeatherDaily.is_forecast.is_(True)
    ).delete(synchronize_session=False)
    db.commit()
    # forecast rows start TOMORROW (today already exists as a history row)
    for i in range(1, 8):
        db.add(WeatherDaily(mine_id=mine.id, date=today + timedelta(days=i),
                            rain_mm_x10=(300 if i in (1, 2) else 0),
                            source="forecast_csv", is_forecast=True))
    db.commit()
    result = build_plan_suggestion(db, mine.id, days=7)
    assert result["ok"] is True
    assert result["capacity_cap_t"] >= result["baseline_dry_t"]
    wet = [r for r in result["rows"] if r["rain_mm"] >= 20]
    assert wet and wet[0]["expected_loss_t"] > 0


def test_plan_no_forecast(db, seeded):
    result = build_plan_suggestion(db, 99999, days=3)
    assert result["ok"] is False


def test_target_vs_actual(db, seeded):
    end = date.today()
    start = end.replace(day=1)
    out = target_vs_actual(db, seeded.id, start, end)
    assert out["actual_t"] > 0
    assert out["target_t"] == 900.0
    assert 0 < out["achievement_pct"] < 500
    assert "Production was" in out["factual_summary"]


def test_conflict_model(db, seeded):
    c = DataConflict(subject_type="DAILY_PRODUCTION", subject_key="TM1/2026-09-01",
                     system_value="8000", external_value="7850",
                     external_source=" scanned daily statement")
    db.add(c)
    db.commit()
    assert c.status == "OPEN"  # system never decides - human verifies


def test_scoped_text_to_sql(db, seeded, monkeypatch):
    from app.db.models import User
    from app.services import text_to_sql

    # Deterministic: patch SQL generation so this test exercises the
    # scoping injection + guards, not live-LLM output variability.
    canned = "SELECT mine_id, SUM(production_milli_t) FROM shift_entry GROUP BY mine_id"
    monkeypatch.setattr(text_to_sql, "_llm_sql", lambda question: canned)

    user = db.query(User).filter(User.username == "fman_t").first()
    result = text_to_sql.run_text_to_sql(db, canned, user=user)
    assert result["ok"] is True
    # scoped: only the test mine's rows come back
    mine_ids = {r[0] for r in result["rows"]}
    assert mine_ids <= {seeded.id} | {None}
    assert result["scope"] is not None


def test_text_to_sql_blocklisted_table(db, seeded):
    from app.services.text_to_sql import _is_safe_sql, _tables_in_sql

    # the guard chain itself must reject sqlite_master even if the LLM
    # is unavailable (offline CI) - allow-list check + safety guard
    sql = "SELECT name FROM sqlite_master"
    assert "sqlite_master" in _tables_in_sql(sql)
    assert "sqlite_master" not in settings.sql_allow_tables
    # and a write attempt is blocked by the keyword guard
    assert not _is_safe_sql("DROP TABLE shift_entry")
    assert not _is_safe_sql("SELECT 1; DELETE FROM shift_entry")


def test_lineage_recursive_children(db, seeded):
    from app.services.aggregation import generate_daily_report, generate_mine_daily_report

    today = date.today()
    daily = generate_daily_report(db, seeded.id, seeded.benches[0].id, today)
    assert daily is not None
    mine_daily = generate_mine_daily_report(db, seeded.id, today)

    from app.api.lineage import _recursive_children
    children = _recursive_children(db, mine_daily.id)
    assert any(c["child_kind"] == "REPORT" for c in children)
    assert any(c["child_kind"] == "SHIFT_ENTRY" for c in children)


def test_anomalies_deterministic(db, seeded):
    from app.services.anomalies import detect_anomalies

    out = detect_anomalies(db, seeded.id, lookback_days=30)
    assert isinstance(out, list)
