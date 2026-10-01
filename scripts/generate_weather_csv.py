"""Generate SAMPLE weather CSVs for the offline planning module.

Writes, per demo mine, into the backend data dir (data_dir/weather/):
  history_<MINECODE>.csv    date,rain_mm,temp_max   (past 2 years, observed)
  forecast_<MINECODE>.csv   date,rain_mm,temp_max   (next 14 days, forecast)

Deterministic (seed 42). Real deployments replace these with IMD/NASA POWER
exports - same column names. Nothing here touches the network.

Usage:
  backend/.venv/Scripts/python.exe scripts/generate_weather_csv.py
"""
from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import settings  # noqa: E402

MINES = ["MINE1", "MINE1A", "MINE2"]
# NE-monsoon profile for Neyveli-like climate: Oct-Dec wettest
RAIN_PROB = {1: .06, 2: .07, 3: .08, 4: .14, 5: .22, 6: .38,
             7: .48, 8: .46, 9: .40, 10: .34, 11: .46, 12: .18}
HEAVY_SHARE = {1: .05, 2: .05, 3: .08, 4: .15, 5: .20, 6: .35,
               7: .45, 8: .42, 9: .35, 10: .30, 11: .40, 12: .12}


def _row(rng: random.Random, d: date, forecast: bool) -> dict:
    p = RAIN_PROB[d.month] * (1.15 if forecast else 1.0)
    if rng.random() < p:
        if rng.random() < HEAVY_SHARE[d.month]:
            rain = round(rng.uniform(20, 90), 1)
        else:
            rain = round(rng.uniform(1, 19), 1)
    else:
        rain = 0.0
    temp = round(31 + 4 * ((d.month % 12) / 12) + rng.uniform(-2, 2), 1)
    return {"date": d.isoformat(), "rain_mm": rain, "temp_max": temp}


def main() -> None:
    out_dir = settings.data_dir / "weather"
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    today = date.today()

    for code in MINES:
        hist_path = out_dir / f"history_{code}.csv"
        if not hist_path.exists():
            with hist_path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["date", "rain_mm", "temp_max"])
                w.writeheader()
                d = today - timedelta(days=730)
                while d < today:
                    w.writerow(_row(rng, d, forecast=False))
                    d += timedelta(days=1)

        fc_path = out_dir / f"forecast_{code}.csv"
        with fc_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["date", "rain_mm", "temp_max"])
            w.writeheader()
            d = today
            while d < today + timedelta(days=14):
                w.writerow(_row(rng, d, forecast=True))
                d += timedelta(days=1)

        print(f"{code}: {hist_path.name} + {fc_path.name} written to {out_dir}")


if __name__ == "__main__":
    main()
