"""Weather data layer for the planning module.

Design (per constraint 1 - air-gapped runtime):
- CsvProvider is the DEFAULT: an operator drops historical daily weather
  and forecast CSVs into data/weather/ ; nothing ever calls the network.
- OpenMeteoProvider exists but is behind WEATHER_ONLINE=true and points at
  an operator-run gateway (weather_online_base_url), so the running app
  still never touches the internet by default.
All rows land in weather_daily(mine_id, date, rain_mm, temp_max_x10,
source, is_forecast, fetched_at). Stale forecasts are surfaced as STALE,
never silently reused.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db.extended_models import WeatherDaily
from app.db.models import Mine

logger = logging.getLogger("minetrace.weather")

RAIN_BINS = [(0.0, 1.0), (1.0, 5.0), (5.0, 20.0), (20.0, 50.0), (50.0, float("inf"))]


def bin_for_rain(rain_mm: float) -> str:
    for lo, hi in RAIN_BINS:
        if lo <= rain_mm < hi:
            if hi == float("inf"):
                return "50+"
            label = f"{lo:g}-{hi:g}"
            return label
    return "0-1"


class WeatherProvider:
    def fetch_daily(self, mine: Mine, start: date, end: date) -> list[dict]:
        raise NotImplementedError


class CsvProvider(WeatherProvider):
    """Reads data/weather/history_<MINECODE>.csv and forecast_<MINECODE>.csv.

    Expected columns: date, rain_mm, temp_max (temp optional).
    Forecast rows (dates >= today) are marked is_forecast=1 with
    source='forecast_csv'.
    """

    def __init__(self) -> None:
        self.dir = settings.data_dir / "weather"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _rows(self, mine: Mine, filename: str) -> list[dict]:
        path = self.dir / filename
        if not path.exists():
            return []
        out = []
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    d = date.fromisoformat(row["date"].strip())
                    out.append({
                        "date": d,
                        "rain_mm": float(row.get("rain_mm") or 0.0),
                        "temp_max": float(row["temp_max"]) if row.get("temp_max") else None,
                    })
                except (ValueError, KeyError):
                    continue
        return out

    def fetch_daily(self, mine: Mine, start: date, end: date) -> list[dict]:
        today = date.today()
        rows = []
        for r in self._rows(mine, f"history_{mine.code}.csv") + self._rows(
            mine, f"forecast_{mine.code}.csv"
        ):
            if start <= r["date"] <= end:
                rows.append({
                    **r,
                    "is_forecast": r["date"] >= today,
                    "source": "forecast_csv" if r["date"] >= today else "history_csv",
                })
        return rows


class OpenMeteoProvider(WeatherProvider):
    """Optional online provider - only used when WEATHER_ONLINE=true.

    Points at weather_online_base_url (an operator-run gateway that proxies
    Open-Meteo), so the app itself talks to localhost only.
    """

    def fetch_daily(self, mine: Mine, start: date, end: date) -> list[dict]:
        if not settings.weather_online:
            return []
        import httpx

        try:
            resp = httpx.get(
                f"{settings.weather_online_base_url}/v1/forecast",
                params={"mine": mine.code, "start": start.isoformat(),
                        "end": end.isoformat()},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return []
            out = []
            for row in resp.json().get("daily", []):
                out.append({
                    "date": date.fromisoformat(row["date"]),
                    "rain_mm": float(row.get("rain_mm") or 0.0),
                    "temp_max": row.get("temp_max"),
                    "is_forecast": True,
                    "source": "open-meteo",
                })
            return out
        except Exception:
            logger.exception("Weather gateway fetch failed")
            return []


def get_provider() -> WeatherProvider:
    if settings.weather_provider == "open-meteo" and settings.weather_online:
        return OpenMeteoProvider()
    return CsvProvider()


def upsert_daily(db: Session, mine: Mine, rows: list[dict]) -> int:
    n = 0
    for r in rows:
        existing = (
            db.query(WeatherDaily)
            .filter(WeatherDaily.mine_id == mine.id, WeatherDaily.date == r["date"])
            .first()
        )
        if existing:
            existing.rain_mm_x10 = int(round(r["rain_mm"] * 10))
            if r.get("temp_max") is not None:
                existing.temp_max_x10 = int(round(float(r["temp_max"]) * 10))
            existing.is_forecast = bool(r.get("is_forecast"))
            existing.source = r.get("source", existing.source)
            existing.fetched_at = datetime.now(timezone.utc)
        else:
            db.add(WeatherDaily(
                mine_id=mine.id,
                date=r["date"],
                rain_mm_x10=int(round(r["rain_mm"] * 10)),
                temp_max_x10=(
                    int(round(float(r["temp_max"]) * 10))
                    if r.get("temp_max") is not None else None
                ),
                is_forecast=bool(r.get("is_forecast")),
                source=r.get("source", "history_csv"),
                fetched_at=datetime.now(timezone.utc),
            ))
        n += 1
    db.flush()
    return n


def forecast_window(db: Session, mine: Mine, days: int) -> tuple[list[WeatherDaily], bool]:
    """Return forecast rows for the next `days` days plus a STALE flag."""
    today = date.today()
    end = date.fromordinal(today.toordinal() + days - 1)
    rows = (
        db.query(WeatherDaily)
        .filter(
            WeatherDaily.mine_id == mine.id,
            WeatherDaily.date >= today,
            WeatherDaily.date <= end,
        )
        .order_by(WeatherDaily.date)
        .all()
    )
    stale = False
    if not rows:
        stale = True
    else:
        latest = max(r.fetched_at for r in rows)
        # SQLite stores naive datetimes; normalize both sides to naive UTC.
        if latest.tzinfo is not None:
            latest = latest.astimezone(timezone.utc).replace(tzinfo=None)
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        age_days = (now_utc - latest).days
        stale = age_days > settings.weather_forecast_stale_days
    return rows, stale


def import_csv_for_all_mines(db: Session) -> dict:
    """Operator entrypoint: import/refresh CSVs for every mine."""
    provider = get_provider()
    result = {}
    for mine in db.query(Mine).all():
        rows = provider.fetch_daily(
            mine, date(2020, 1, 1), date.fromordinal(date.today().toordinal() + 30)
        )
        result[mine.code] = upsert_daily(db, mine, rows)
    return result
