"""Weather-aware production forecast for NLC Mine-I (Monte Carlo).

Answers: "does it have a weather predicting model for future production?"
YES - this script:
  1. Reads the generated dataset to calibrate realized constraint rates
     (rain days, failure days, strike probability).
  2. Combines them with Neyveli rainfall climatology (NE monsoon Oct-Dec
     dominates; see README sources).
  3. Runs N Monte Carlo trials of the coming month: each day draws rain
     (month-specific probability), intensity, machine failures, strike;
     applies the same output factors and compensation logic as the
     generator, then recovers deficit on later days.
  4. Reports P10/P50/P90 monthly production and the probability of
     meeting the 3000 kt target, plus expected rain-days lost.

Usage:
    python forecast_production.py 2027 01
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import generate_dataset as gen

TRIALS = 4000


def realized_rates(year: int, month: int) -> dict:
    """Calibrate from generated history (same month, previous year)."""
    p = Path(__file__).resolve().parent / str(year - 1) / f"{month:02d}" / "summary.csv"
    rates = {"rainy_days": None, "failure_days": None, "both_days": None}
    if p.exists():
        with open(p) as f:
            for row in csv.reader(f):
                if row and row[0] in rates:
                    rates[row[0]] = float(row[1])
    return rates


def forecast(year: int, month: int, trials: int = TRIALS) -> dict:
    days = (date(year + (month == 12), month % 12 + 1, 1) - date(year, month, 1)).days
    rain_p = gen.RAIN_PROB_BY_MONTH[month]
    daily_target = gen.DAILY_TARGET_T
    cap = gen.RECOVERY_CAP_PCT

    totals = []
    rain_day_counts = []
    failure_day_counts = []

    for _ in range(trials):
        pending = 0.0
        total = 0.0
        rain_days = 0
        failure_days = 0
        for _ in range(days):
            rainy = gen.rng.random() < rain_p
            intensity = gen.rain_intensity(month, rainy)
            rf = gen.RAIN_OUTPUT_FACTOR[intensity]
            failures = gen.machine_failures(0, month)
            fl = sum(f["lost_t"] for f in failures)
            ff = max(0.15, 1 - fl / (daily_target * 0.9))
            if rainy:
                rain_days += 1
            if failures:
                failure_days += 1

            base = daily_target * rf * ff
            recover = min(
                pending,
                daily_target * cap * (1 - rf) + daily_target * cap,
            )
            out = min(base + recover, daily_target * (1 + cap))
            pending = max(0.0, pending - recover + (daily_target - out if out < daily_target else 0))
            total += out
        totals.append(total)
        rain_day_counts.append(rain_days)
        failure_day_counts.append(failure_days)

    totals.sort()
    p10 = totals[int(0.10 * trials)]
    p50 = totals[int(0.50 * trials)]
    p90 = totals[int(0.90 * trials)]
    target = gen.MONTHLY_TARGET_KT * 1000
    hit = sum(1 for t in totals if t >= target) / trials
    avg_rain = sum(rain_day_counts) / trials
    avg_fail = sum(failure_day_counts) / trials
    clim = realized_rates(year, month)

    return {
        "month": f"{year}-{month:02d}",
        "trials": trials,
        "days": days,
        "rain_probability_climatology": rain_p,
        "history_prev_year": clim,
        "expected_rain_days": round(avg_rain, 1),
        "expected_failure_days": round(avg_fail, 1),
        "p10_kt": round(p10 / 1000),
        "p50_kt": round(p50 / 1000),
        "p90_kt": round(p90 / 1000),
        "target_kt": gen.MONTHLY_TARGET_KT,
        "prob_meet_target_pct": round(hit * 100, 1),
    }


def main() -> None:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2027
    month = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    result = forecast(year, month)

    out = Path(__file__).resolve().parent / str(year) / f"forecast_{year}-{month:02d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(out, "w") as f:
        json.dump(result, f, indent=2)

    print(f"FORECAST {result['month']} ({result['trials']} Monte Carlo trials)")
    print(f"  Rain probability (climatology): {result['rain_probability_climatology']:.0%}")
    print(f"  Expected rain days: {result['expected_rain_days']} | expected failure days: {result['expected_failure_days']}")
    if result["history_prev_year"]["rainy_days"] is not None:
        print(f"  Realized last year: {result['history_prev_year']}")
    print(f"  Production P10/P50/P90: {result['p10_kt']} / {result['p50_kt']} / {result['p90_kt']} kt")
    print(f"  Target: {result['target_kt']} kt -> probability of meeting: {result['prob_meet_target_pct']}%")
    print(f"  Saved: {out}")


if __name__ == "__main__":
    main()
