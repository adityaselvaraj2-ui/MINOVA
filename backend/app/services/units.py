from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MILLI = 1000


def milli_to_display(value_int: int, decimals: int = 3) -> str:
    d = Decimal(value_int) / Decimal(MILLI)
    if decimals == 0:
        return str(int(d.to_integral_value(rounding=ROUND_HALF_UP)))
    fmt = f"{{:.{decimals}f}}"
    return fmt.format(float(d))


def display_to_milli(value: float | str) -> int:
    d = Decimal(str(value)) * Decimal(MILLI)
    return int(d.to_integral_value(rounding=ROUND_HALF_UP))


def compute_ratio(numerator_int: int, denominator_int: int, decimals: int = 4) -> str | None:
    if denominator_int == 0:
        return None
    d = Decimal(numerator_int) / Decimal(denominator_int)
    fmt = f"{{:.{decimals}f}}"
    return fmt.format(float(d))


def compute_percentage(part_int: int, whole_int: int, decimals: int = 2) -> str | None:
    if whole_int == 0:
        return None
    d = (Decimal(part_int) / Decimal(whole_int)) * Decimal(100)
    fmt = f"{{:.{decimals}f}}"
    return fmt.format(float(d))
