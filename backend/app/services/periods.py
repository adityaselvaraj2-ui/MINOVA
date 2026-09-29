from __future__ import annotations

import calendar
from datetime import date

MONTH_CLIPPED_BREAKS = [1, 8, 15, 22, 29]


def month_clipped_weeks(year: int, month: int) -> list[tuple[date, date]]:
    last_day = calendar.monthrange(year, month)[1]
    weeks = []
    for i, start_day in enumerate(MONTH_CLIPPED_BREAKS):
        if start_day > last_day:
            break
        if i + 1 < len(MONTH_CLIPPED_BREAKS):
            end_day = min(MONTH_CLIPPED_BREAKS[i + 1] - 1, last_day)
        else:
            end_day = last_day
        weeks.append((date(year, month, start_day), date(year, month, end_day)))
    return weeks


def week_for_date(d: date) -> tuple[date, date]:
    for start, end in month_clipped_weeks(d.year, d.month):
        if start <= d <= end:
            return (start, end)
    msg = f"Date {d} not in any MONTH_CLIPPED week"
    raise ValueError(msg)


def month_boundaries(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return (date(year, month, 1), date(year, month, last_day))


def quarter_boundaries(year: int, quarter: int) -> tuple[date, date]:
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    last_day = calendar.monthrange(year, end_month)[1]
    return (date(year, start_month, 1), date(year, end_month, last_day))


def quarter_for_month(month: int) -> int:
    return (month - 1) // 3 + 1


def year_boundaries(year: int) -> tuple[date, date]:
    return (date(year, 1, 1), date(year, 12, 31))


CHILD_LEVEL = {
    "WEEKLY": "DAILY",
    "MONTHLY": "WEEKLY",
    "QUARTERLY": "MONTHLY",
    "HALF_YEARLY": "MONTHLY",
    "ANNUAL": "QUARTERLY",
}


def expected_children_for_daily(shift_codes: list[str]) -> int:
    return len(shift_codes)


def child_periods(
    level: str, period_start: date, period_end: date,
) -> list[tuple[date, date]]:
    if level == "WEEKLY":
        d = period_start
        periods = []
        while d <= period_end:
            periods.append((d, d))
            d = date.fromordinal(d.toordinal() + 1)
        return periods

    if level == "MONTHLY":
        return month_clipped_weeks(period_start.year, period_start.month)

    if level == "QUARTERLY":
        q = quarter_for_month(period_start.month)
        start_month = (q - 1) * 3 + 1
        periods = []
        for m in range(start_month, start_month + 3):
            periods.append(month_boundaries(period_start.year, m))
        return periods

    if level == "ANNUAL":
        periods = []
        for q in range(1, 5):
            periods.append(quarter_boundaries(period_start.year, q))
        return periods

    return []
