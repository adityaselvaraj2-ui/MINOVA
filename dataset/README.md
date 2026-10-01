# NLC Mine-I Production Dataset (SIH26023 demo corpus)

SYNTHETIC, demo-only dataset that models daily lignite production of NLC India
Ltd's Neyveli Mine-I with the constraints you specified, foldered exactly as
asked:

```
dataset/
├── generate_dataset.py        # generator (all logic + calibration constants)
├── forecast_production.py     # weather-aware Monte Carlo production forecast
├── 2025/                      # one folder per year
│   ├── year_summary.csv       # month-by-month totals, rain/failure day counts
│   ├── 01/ ... 12/            # month folders
│   │   ├── summary.csv        # production vs target, rain/failure/strike days
│   │   ├── daily_flat.csv     # flat day rows for quick analysis
│   │   ├── monthly_report.md  # human-readable NLC-style monthly report
│   │   ├── week-1/ ... week-5/    # MONTH-CLIPPED weeks (1-7, 8-14, ...)
│   │   │   ├── summary.csv    # per-day rows + week total
│   │   │   └── day-01/ ...        # one folder per day│   │   │   ├── production.csv # per-machine rows (NLC stoppage-report style)
│   │   │       └── events.json    # rain / failure / strike events of that day
│   │   ├── stoppage_log.csv       # timestamped per-event log -> Pareto analytics
│   │   ├── machine_utilization.csv # per-machine planned vs effective hours
│   └── 2026/                  # second year
├── targets_validation.csv     # target provenance + arithmetic audit trail
└── 2027/forecast_2027-11.json # example weather-based forecast output
```

## What the data shows

- **Target (validated): 875 kt/month (~29,167 t/day)** = NLC Mine-I official
  capacity of 10.5 MTPA / 12. The audit trail lives in
  `targets_validation.csv` (every constant: value, unit, source, validation).
  The earlier 3,000 kt/month example equals all three Neyveli mines combined
  and is documented there as superseded.
- **Rainy day:** output drops to 72% (moderate rain) or 35% (heavy rain,
  NE monsoon Oct–Dec).
- **Machine failure:** Poisson events per BWE (3%/machine/day, 0.5–4 h) with
  real causes lifted from the genuine `M-1 STOPPAGE on 07.09.2026` NLC report
  (BWE repositioning, conveyor point changing, roller-support welding,
  waiting for NNTPP conveyor, machine tripped while steering...).
- **Rain + failure:** factors multiply (compounding).
- **Compensation:** the lost tonnes are recovered over following days up to
  +18%/day extended-hours catch-up — exactly the "extra work next day"
  behavior you described. See any `monthly_report.md` "Compensation" section.
- **Supply:** never an issue (constraint 4 honored).
- **Accidents/blasts:** not simulated (constraint 5 - rare/unpredictable).
- **Strike:** 0.05 probability per YEAR (constraint 6), one zero-output day
  if it fires.

## Previous-Year Production Report

`generate_pypr.py` renders **Previous_Year_Production_Report_2025.docx / .pdf**:
a polished annual report with executive summary, three embedded charts
(production-vs-target bars, rain-impact box plot, downtime Pareto with
cumulative %), month-wise table and a data-provenance section. Headline:
**10,381 kt vs 10,646 kt target (97.5%)**. Every figure is computed
deterministically from the dataset CSVs.

## The weather model (your last question)

`forecast_production.py` **is** the weather-predicting model for future
production:

1. Takes month-specific rain probability from Neyveli climatology
   (NE monsoon Oct–Dec is the wet window; June–Sep SW monsoon secondary).
2. Calibrates against last year's *realized* rain/failure days from the
   dataset itself.
3. Runs 4,000 Monte Carlo trials of the month: each day draws rain,
   intensity, machine failures; applies the same factors and catch-up logic.
4. Outputs **P10/P50/P90 production**, expected rain days, and the
   **probability of hitting the 3,000 kt target**.

Example (already generated):

| Month | Rain prob | Expected rain days | P50 | P(meet 3000 kt) |
|---|---|---|---|---|
| 2027-01 (dry) | 6% | 1.9 | 3,098 kt | 100% |
| 2027-11 (NE monsoon) | 46% | 13.7 | 2,795 kt | 0% |

→ Management takeaway the model gives: in monsoon months either plan a lower
target, pre-position maintenance before October, or arrange additional
recovery capacity.

Run it yourself:

```bash
cd dataset
../backend/.venv/Scripts/python.exe forecast_production.py 2027 11
```

## Calibration sources (cross-checked online)

| Constant | Source |
|---|---|
| BWE rates ~500 t/h, 18.45 h shifts, per-machine output format, stoppage causes | Your real `M-1 STOPPAGE on 07.09.2026.pdf` (NLC India Ltd header, Mine-I) |
| Shift report structure (B1 RELAY, 1st shift, LBS-M1) | Your `08-09-2026-B1 RELAY- 1st SHIFT -LBS-M1.pdf` |
| Mine-I capacity 10.5 MTPA (875 kt/mo), Mine-IA 3.0, Mine-II 15.0 | nlcindia.in annual reports & environmentclearance.nic.in Mine-II EC note |
| NE monsoon Oct–Dec dominant (~48% of annual rain; Oct ~180 mm, Nov ~240 mm) | IMD/Mausam journal, MASU journal, ResearchGate Neyveli rainfall studies |
| Tamil Nadu normal NE-monsoon quota ~444 mm | IMD seasonal reports |

**Note on scale:** the 3,000 kt/month target you gave equals all three Neyveli
mines combined (Mine-I 10.5 + Mine-IA 3.0 + Mine-II 15.0 ≈ 28.5 MTPA →
~2,375 kt/mo); Mine-I alone would target ~875 kt/mo. The target is one
constant (`MONTHLY_TARGET_KT`) — set it to 875 for Mine-I-only realism.

## Regenerate / tweak

Everything is deterministic (seed 42):

```bash
cd dataset
../backend/.venv/Scripts/python.exe generate_dataset.py
```

Knobs at the top of `generate_dataset.py`: `MONTHLY_TARGET_KT`,
`RAIN_PROB_BY_MONTH`, `RAIN_OUTPUT_FACTOR`, `FAILURE_PROB_PER_MACHINE`,
`FAILURE_HOURS`, `STRIKE_PROB_PER_YEAR`, `RECOVERY_CAP_PCT`, fleet table.

## Remaining constraints worth adding (your question)

Your six are the right operational set. From the real report + NLC context,
these are the ones I'd add next, in impact order:

1. **Power/supply-grid trip** — NLC mines are captive-power driven; grid
   dips trip BWEs (the real report shows "Cum stop - M/C tripped while
   steering" style events). Modeled implicitly inside machine failures today.
2. **Planned annual maintenance shutdown (OEM major OH)** — weeks-long,
   pre-planned; different from random failures (the real report shows a
   "Major OH work (stoppage from 16.07.2026)" continuing 3+ weeks).
3. **Conveyor/NNTPP downstream bottleneck** — mine output is capped by
   pit-head conveyor availability ("Waiting for NNTPP conveyor" in the real
   report), independent of excavator health.
4. **Holidays/shift shortages** (Diwali/Pongal roster effects) — small but
   systematic.
5. **Stripping-ratio/OB priority phases** — some days OB removal is pushed
   over lignite, cutting lignite output without any "failure".
6. **Fire in coal stock / high-temperature spells** — summer hazard at
   lignite yards (self-combustion), localized impact.
