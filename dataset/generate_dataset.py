"""NLC Mine-I synthetic production dataset generator (SIH26023 demo corpus).

Models daily lignite production of NLC India Mine-I (Neyveli) with the
constraints that affect output:
  1. Rainy days (from Neyveli climatology - NE monsoon Oct-Dec dominates)
  2. Machine failure (Poisson events, durations calibrated from the real
     "M-1 STOPPAGE on 07.09.2026" NLC stoppage report)
  3. Both rain + failure (compounding)
  4. Supply issues: ZERO (per operator input - NLC has backup supply)
  5. Accidents/blasts: excluded (rare, unpredictable - noted, not simulated)
  6. Workers strike: 0.05 probability per YEAR, not per day

Compensation logic: when a day loses production to rain/failure, the shortfall
is recovered over the following days by extended hours (EH) up to a per-day
recovery cap - mirroring how the real NLC stoppage report plans catch-up.

Monthly target: 3000 thousand tonnes (3.0 MT) lignite for Mine-I scale.
All data is SYNTHETIC for demo purposes; calibration constants come from the
real stoppage report and public NLC/climatology sources (see README).
"""
from __future__ import annotations

import calendar
import csv
import json
import random
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------- calibration
# Fleet modeled from "M-1 STOPPAGE on 07.09.2026.pdf" (real NLC Mine-I report):
#   LBS/BWE-1029 LIGNITE: TWH 18.45, EWH 18.45, Output 9,600.000 t, Rate 512 t/h
#   LBS/BWE-1029 OVER BURDEN: output 0 (stoppage day)
# Fleet right-sized to Mine-I scale: the real stoppage report shows one BWE
# (LBS/BWE-1029) producing 9,600 t in 18.45 h (520 t/h). ~29 kt/day target
# => 4 main lignite BWEs + 2 short-shift LHS units. Nominal capacity
# ~45.7 kt/day => ~64% utilization at target, leaving catch-up headroom.
FLEET = [
    # (machine_id, seam, nominal_rate_tph, planned_hours)
    ("LBS/BWE-1029", "LIGNITE", 520, 18.45),
    ("LBS/BWE-1030", "LIGNITE", 500, 18.45),
    ("MBS/BWE-1648", "LIGNITE", 470, 18.45),
    ("NSB/BWE-1357", "LIGNITE", 510, 18.45),
    ("LHS/BWE-147", "LIGNITE", 450, 10.00),
    ("LHS/BWE-148", "LIGNITE", 430, 10.00),
]
OB_RATE_TPH = 900  # combined overburden removal rate for the fleet

MONTHLY_TARGET_KT = 875  # thousand tonnes/month = Mine-I 10.5 MTPA (nlcindia.in)
# Validated target (see README - Sources): NLC Mine-I nominal capacity is
# 10.5 MTPA => 875 kt/month, ~29,167 t/day. Source: NLC India annual reports
# and the Mine-II environmental clearance note (environmentclearance.nic.in).
DAILY_TARGET_T = MONTHLY_TARGET_KT * 1000 / 30.0  # ~29,167 t/day
RECOVERY_CAP_PCT = 0.18   # max extra production a catch-up day can add
RAIN_PROB_BY_MONTH = {    # Neyveli (Cuddalore dist.) climatology
    1: 0.06, 2: 0.05, 3: 0.06, 4: 0.10, 5: 0.16, 6: 0.24,
    7: 0.26, 8: 0.28, 9: 0.30, 10: 0.42, 11: 0.46, 12: 0.36,
}
RAIN_OUTPUT_FACTOR = {0: 1.00, 1: 0.72, 2: 0.35}  # intensity -> output factor
FAILURE_PROB_PER_MACHINE = 0.030   # daily chance a BWE needs unplanned stoppage
FAILURE_HOURS = (0.5, 4.0)         # min/max unplanned downtime hours
STRIKE_PROB_PER_YEAR = 0.05
YEAR_START = 2025
YEAR_END = 2026

rng = random.Random(42)


def rain_intensity(month: int, rainy: bool) -> int:
    if not rainy:
        return 0
    # NE-monsoon months get more intense spells
    heavy_bias = 0.35 if month in (10, 11, 12) else 0.15
    return 2 if rng.random() < heavy_bias else 1


def machine_failures(day_idx: int, month: int) -> list[dict]:
    failures = []
    for mid, seam, rate, hours in FLEET:
        if rng.random() < FAILURE_PROB_PER_MACHINE:
            dur = round(rng.uniform(*FAILURE_HOURS), 2)
            failures.append({
                "machine": mid,
                "duration_h": dur,
                "cause": rng.choice([
                    "BWE track area preparation & repositioning",
                    "Conveyor sequence feeding point changing",
                    "Daily maintenance overrun",
                    "Vertical roller support structure welding",
                    "Cum stop - M/C tripped while steering",
                    "Waiting for NNTPP conveyor",
                ]),
                "lost_t": round(rate * dur),
            })
    return failures


def strike_this_year(year: int) -> bool:
    return rng.random() < STRIKE_PROB_PER_YEAR


def simulate_month(year: int, month: int) -> list[dict]:
    days_in_month = calendar.monthrange(year, month)[1]
    rain_p = RAIN_PROB_BY_MONTH[month]
    is_strike_year = strike_this_year(year)
    strike_day = rng.randint(1, days_in_month) if is_strike_year else None

    pending_deficit = 0.0
    rows = []

    for d in range(1, days_in_month + 1):
        day = date(year, month, d)
        rainy = rng.random() < rain_p
        intensity = rain_intensity(month, rainy)
        rain_factor = RAIN_OUTPUT_FACTOR[intensity]

        failures = machine_failures(d, month)
        failure_lost_t = sum(f["lost_t"] for f in failures)
        failure_factor = max(0.15, 1 - failure_lost_t / (DAILY_TARGET_T * 0.9))

        on_strike = (strike_day == d)
        if on_strike:
            output = 0.0
            ob = 0.0
        else:
            base = DAILY_TARGET_T * rain_factor * failure_factor
            # recovery: add up to cap of target when carrying deficit
            recover = min(
                pending_deficit,
                DAILY_TARGET_T * RECOVERY_CAP_PCT * (1 - rain_factor) + DAILY_TARGET_T * RECOVERY_CAP_PCT,
            )
            output = min(base + recover, DAILY_TARGET_T * (1 + RECOVERY_CAP_PCT))
            pending_deficit = max(0.0, pending_deficit - recover + (DAILY_TARGET_T - output if output < DAILY_TARGET_T else 0))
            ob = round(OB_RATE_TPH * 18.45 * rain_factor * failure_factor)

        events = []
        if rainy:
            events.append({
                "type": "RAIN",
                "intensity": {1: "moderate", 2: "heavy"}[intensity],
                "output_factor": rain_factor,
            })
        events.extend({"type": "MACHINE_FAILURE", **f} for f in failures)
        if on_strike:
            events.append({"type": "STRIKE", "note": "rare industrial action (p=0.05/yr)"})

        rows.append({
            "date": day.isoformat(),
            "rainy": rainy,
            "rain_intensity": intensity,
            "machine_failures": len(failures),
            "failure_lost_t": failure_lost_t,
            "strike": on_strike,
            "production_t": round(output),
            "overburden_m3": ob,
            "target_t": round(DAILY_TARGET_T),
            "events": events,
        })

    return rows


def _write_month_report(
    month_dir: Path, year: int, month: int,
    rows: list[dict], total: float, target: float,
) -> None:
    """Human-readable monthly report in the style of NLC Mine reports."""
    month_name = calendar.month_name[month]
    rainy = [r for r in rows if r["rainy"]]
    worst = min(rows, key=lambda r: r["production_t"])
    compensated = [
        r for r in rows
        if r["production_t"] > r["target_t"]
    ]
    lines = [
        f"# NLC INDIA LTD - Mine-I Production Report: {month_name} {year}",
        "",
        "*SYNTHETIC demo dataset for SIH26023 - calibrated from the real "
        "M-1 Stoppage Report 07.09.2026. Not actual production.*",
        "",
        "## Headline figures",
        f"- Lignite production: **{total/1000:,.0f} kt** against target "
        f"{target/1000:,.0f} kt ({100*total/target:.1f}%)",
        f"- Rainy days: {len(rainy)} | Machine-failure days: "
        f"{sum(1 for r in rows if r['machine_failures'])} | "
        f"Both: {sum(1 for r in rows if r['rainy'] and r['machine_failures'])} "
        f"| Strike days: {sum(1 for r in rows if r['strike'])}",
        f"- Worst day: {worst['date']} at {worst['production_t']:,} t "
        f"({100*worst['production_t']/worst['target_t']:.0f}% of target)",
        "",
        "## Constraint log (days affected)",
    ]
    for r in rows:
        if r["events"]:
            ev = "; ".join(
                (f"RAIN({e['intensity']})" if e["type"] == "RAIN"
                 else f"FAILURE {e['machine']} {e['duration_h']}h - {e['cause']}"
                 if e["type"] == "MACHINE_FAILURE" else "STRIKE")
                for e in r["events"]
            )
            lines.append(
                f"- **{r['date']}**: {ev} -> {r['production_t']:,} t "
                f"({100*r['production_t']/r['target_t']:.0f}%)"
            )
    lines += ["", "## Compensation (catch-up days above target)"]
    if compensated:
        for r in compensated:
            lines.append(
                f"- {r['date']}: {r['production_t']:,} t "
                f"(+{100*(r['production_t']-r['target_t'])/r['target_t']:.0f}% over target)"
            )
    else:
        lines.append("- None this month (deficit carried, no recovery days triggered)")
    lines += [
        "",
        "## Method note",
        "Loss days cut output via rain-intensity and machine-downtime factors; "
        "the deficit is recovered over following days up to +18%/day (extended "
        "hours), mirroring NLC catch-up practice in the real stoppage report.",
        "",
    ]
    (month_dir / "monthly_report.md").write_text("\n".join(lines))


STOPPAGE_CATEGORY = {
    "Daily maintenance overrun": "maintenance",
    "Vertical roller support structure welding": "maintenance",
    "BWE track area preparation & repositioning": "repositioning",
    "Conveyor sequence feeding point changing": "planned_shifting",
    "Cum stop - M/C tripped while steering": "electrical_trip",
    "Waiting for NNTPP conveyor": "awaiting_infrastructure",
}


def _stoppage_log(month_dir: Path, rows: list[dict]) -> None:
    """Flat per-event stoppage log (enables downtime Pareto + utilization
    analytics, cf. teammate's /analytics/stoppage_pareto)."""
    path = month_dir / "stoppage_log.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "machine", "stop_start_min", "stop_end_min",
                    "duration_h", "category", "description"])
        for r in rows:
            for ev in r["events"]:
                if ev["type"] != "MACHINE_FAILURE":
                    continue
                planned_min = 1107  # 18.45 h shift
                seed = hash((r["date"], ev["machine"])) % (2**32)
                start = random.Random(seed).randint(0, max(0, planned_min - int(ev["duration_h"] * 60)))
                w.writerow([
                    r["date"], ev["machine"], start,
                    start + int(ev["duration_h"] * 60),
                    ev["duration_h"],
                    STOPPAGE_CATEGORY.get(ev["cause"], "other"),
                    ev["cause"],
                ])


def _machine_utilization(month_dir: Path, rows: list[dict]) -> None:
    """Per-machine planned vs effective hours + output (cf. teammate's
    /analytics/machine_utilization EWH/TWH)."""
    stats: dict[str, dict] = {}
    for r in rows:
        with open(month_dir / f"week-{week_of(date.fromisoformat(r['date']))}"
                  f"/day-{r['date'][8:10]}" / "production.csv") as f:
            for row in list(csv.DictReader(f)):
                s = stats.setdefault(row["machine"], {
                    "planned_h": 0.0, "effective_h": 0.0, "output_t": 0})
                s["planned_h"] += float(row["planned_h"])
                s["effective_h"] += float(row["effective_h"])
                s["output_t"] += int(row["output_t"])
    with open(month_dir / "machine_utilization.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["machine", "planned_h", "effective_h", "utilization_pct", "output_t"])
        for mid in sorted(stats):
            s = stats[mid]
            util = 100 * s["effective_h"] / s["planned_h"] if s["planned_h"] else 0
            w.writerow([mid, round(s["planned_h"], 2), round(s["effective_h"], 2),
                        round(util, 1), s["output_t"]])


def _targets_validation(base: Path) -> None:
    """Target provenance + arithmetic validation (audit trail)."""
    fleet_cap = sum(rate * hours for _, _, rate, hours in FLEET)
    rows = [
        ["constant", "value", "unit", "source", "validation"],
        ["MONTHLY_TARGET_KT", MONTHLY_TARGET_KT, "kt/month",
         "NLC Mine-I capacity 10.5 MTPA / 12 (NLC India annual reports; "
         "environmentclearance.nic.in Mine-II EC capacity table)",
         f"12 x {MONTHLY_TARGET_KT} = {12 * MONTHLY_TARGET_KT} kt = "
         f"{12 * MONTHLY_TARGET_KT / 1000:.1f} MTPA = official Mine-I capacity"],
        ["DAILY_TARGET_T", round(DAILY_TARGET_T), "t/day",
         "MONTHLY_TARGET_KT x 1000 / 30", "arithmetic"],
        ["BWE_LIGNITE_RATE", 520, "t/h",
         "Real M-1 STOPPAGE 07.09.2026: LBS/BWE-1029 output 9,600 t / EWH 18.45 h",
         "from source document"],
        ["SHIFT_TWH", 18.45, "h",
         "Real M-1 STOPPAGE 07.09.2026 TWH column", "from source document"],
        ["FLEET_NOMINAL_CAPACITY", round(fleet_cap), "t/day",
         "Sum(rate x planned_h) over the 6-machine Mine-I fleet",
         f"utilization at target = {100 * DAILY_TARGET_T / fleet_cap:.0f}% "
         "(headroom for catch-up days)"],
        ["NOTE_3000KT", 3000, "kt/month",
         "User example: equals all three Neyveli mines combined "
         "(Mine-I 10.5 + Mine-IA 3.0 + Mine-II 15.0 = 28.5 MTPA -> ~2,375 kt/mo)",
         "superseded by validated 875 kt/month for Mine-I"],
    ]
    with open(base / "targets_validation.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)


def week_of(day: date) -> int:
    # MONTH-CLIPPED weeks: 1-7, 8-14, 15-21, 22-28, 29-end (matches MineTrace)
    return (day.day - 1) // 7 + 1


def write_outputs(base: Path, year: int, month: int, rows: list[dict]) -> None:
    month_dir = base / str(year) / f"{month:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)

    # day folders
    for r in rows:
        d = date.fromisoformat(r["date"])
        day_dir = month_dir / f"week-{week_of(d)}" / f"day-{d.day:02d}"
        day_dir.mkdir(parents=True, exist_ok=True)
        with open(day_dir / "production.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["machine", "seam", "output_t", "rate_tph", "planned_h", "effective_h", "remarks"])
            # Distribute the day's output across the fleet proportional to
            # capacity (rate x planned_h); effective_h = output / rate.
            capacities = [rate * hours for _, _, rate, hours in FLEET]
            cap_total = sum(capacities)
            remaining = r["production_t"]
            for i, (mid, seam, rate, hours) in enumerate(FLEET):
                if r["production_t"] == 0:
                    out_i = 0
                elif i == len(FLEET) - 1:
                    out_i = remaining  # last machine absorbs rounding
                else:
                    out_i = round(r["production_t"] * capacities[i] / cap_total)
                    remaining -= out_i
                eff_h = round(out_i / rate, 2) if rate else 0
                remarks = "OK"
                if r["rainy"]:
                    remarks = "RAIN"
                if any(f["machine"] == mid for f in r["events"] if f["type"] == "MACHINE_FAILURE"):
                    remarks = "MACHINE_FAILURE"
                w.writerow([mid, seam, out_i, rate, hours, eff_h, remarks])
        with open(day_dir / "events.json", "w") as f:
            json.dump(r, f, indent=2)

    # week summaries
    for wk in sorted({week_of(date.fromisoformat(r["date"])) for r in rows}):
        wrows = [r for r in rows if week_of(date.fromisoformat(r["date"])) == wk]
        with open(month_dir / f"week-{wk}" / "summary.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "rainy", "rain_intensity", "machine_failures", "production_t", "target_t", "achievement_pct"])
            for r in wrows:
                w.writerow([r["date"], r["rainy"], r["rain_intensity"], r["machine_failures"],
                            r["production_t"], r["target_t"], round(100 * r["production_t"] / r["target_t"], 1)])
            w.writerow(["TOTAL", "", "", sum(r["machine_failures"] for r in wrows),
                        sum(r["production_t"] for r in wrows), sum(r["target_t"] for r in wrows),
                        round(100 * sum(r["production_t"] for r in wrows) / max(1, sum(r["target_t"] for r in wrows)), 1)])

    # month summary
    total = sum(r["production_t"] for r in rows)
    target = sum(r["target_t"] for r in rows)
    rainy_days = sum(1 for r in rows if r["rainy"])
    failure_days = sum(1 for r in rows if r["machine_failures"])
    both_days = sum(1 for r in rows if r["rainy"] and r["machine_failures"])
    with open(month_dir / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["month", f"{year}-{month:02d}"])
        w.writerow(["production_kt", round(total / 1000)])
        w.writerow(["target_kt", round(target / 1000)])
        w.writerow(["achievement_pct", round(100 * total / target, 1)])
        w.writerow(["rainy_days", rainy_days])
        w.writerow(["failure_days", failure_days])
        w.writerow(["rain_and_failure_days", both_days])
        w.writerow(["strike_days", sum(1 for r in rows if r["strike"])])

    _write_month_report(month_dir, year, month, rows, total, target)
    _stoppage_log(month_dir, rows)
    _machine_utilization(month_dir, rows)

    # year summary is assembled after all months
    with open(month_dir / "daily_flat.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "rainy", "rain_intensity", "machine_failures", "failure_lost_t",
                    "strike", "production_t", "overburden_m3", "target_t", "achievement_pct"])
        for r in rows:
            w.writerow([r["date"], r["rainy"], r["rain_intensity"], r["machine_failures"],
                        r["failure_lost_t"], r["strike"], r["production_t"], r["overburden_m3"],
                        r["target_t"], round(100 * r["production_t"] / r["target_t"], 1)])


def write_year_summary(base: Path, year: int) -> None:
    year_dir = base / str(year)
    all_rows = []
    for m in range(1, 13):
        p = year_dir / f"{m:02d}" / "daily_flat.csv"
        if p.exists():
            with open(p) as f:
                all_rows.extend(list(csv.DictReader(f)))

    by_month: dict[int, list] = {}
    for r in all_rows:
        by_month.setdefault(int(r["date"][5:7]), []).append(r)

    with open(year_dir / "year_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "production_kt", "rainy_days", "failure_days", "both_days", "achievement_pct"])
        grand = 0
        for m in range(1, 13):
            if m not in by_month:
                continue
            rows = by_month[m]
            prod = sum(int(r["production_t"]) for r in rows)
            grand += prod
            w.writerow([f"{year}-{m:02d}", round(prod / 1000),
                        sum(1 for r in rows if r["rainy"] == "True"),
                        sum(1 for r in rows if int(r["machine_failures"]) > 0),
                        sum(1 for r in rows if r["rainy"] == "True" and int(r["machine_failures"]) > 0),
                        round(100 * prod / sum(int(r["target_t"]) for r in rows), 1)])
        w.writerow(["TOTAL", round(grand / 1000), "", "", "", ""])


def main() -> None:
    base = Path(__file__).resolve().parent
    _targets_validation(base)
    for year in range(YEAR_START, YEAR_END + 1):
        for month in range(1, 13):
            rows = simulate_month(year, month)
            write_outputs(base, year, month, rows)
        write_year_summary(base, year)
    print(f"Dataset written to {base}")
    print(f"Daily target: {DAILY_TARGET_T:,.0f} t | Monthly target: {MONTHLY_TARGET_KT} kt")


if __name__ == "__main__":
    main()
