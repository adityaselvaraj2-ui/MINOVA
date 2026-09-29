from __future__ import annotations

import re

_NUMBER_RE = re.compile(
    r"(?<![a-zA-Z])"
    r"(\d[\d,]*\.?\d*)"
    r"(?![a-zA-Z])"
)


def extract_numbers(text: str) -> list[str]:
    raw = _NUMBER_RE.findall(text)
    normalized = []
    for n in raw:
        clean = n.replace(",", "")
        if clean in ("0", "1", "2", "3"):
            continue
        normalized.append(clean)
    return normalized


def _normalize(val: str) -> set[str]:
    forms = set()
    forms.add(val)
    try:
        f = float(val)
        forms.add(str(int(f)) if f == int(f) else str(f))
        forms.add(f"{f:.0f}")
        forms.add(f"{f:.1f}")
        forms.add(f"{f:.2f}")
        forms.add(f"{f:.3f}")
        if f >= 1000:
            forms.add(f"{f:,.0f}")
            forms.add(f"{f:,.2f}")
            forms.add(f"{f:,.3f}")
    except ValueError:
        pass
    return forms


def build_allowed_set(fact_sheet: dict) -> set[str]:
    allowed: set[str] = set()

    for key, val in fact_sheet.items():
        if key.startswith("_"):
            continue
        if isinstance(val, (int, float)):
            allowed |= _normalize(str(val))
        elif isinstance(val, str):
            for n in _NUMBER_RE.findall(val):
                allowed |= _normalize(n.replace(",", ""))
        elif isinstance(val, dict):
            for sub_val in val.values():
                if isinstance(sub_val, dict):
                    for v in sub_val.values():
                        if isinstance(v, (int, float)):
                            allowed |= _normalize(str(v))
                        elif isinstance(v, str):
                            for n in _NUMBER_RE.findall(v):
                                allowed |= _normalize(n.replace(",", ""))

    return allowed


def guard_check(text: str, fact_sheet: dict) -> dict:
    extracted = extract_numbers(text)
    allowed = build_allowed_set(fact_sheet)
    violations = []

    for num in extracted:
        if num not in allowed:
            clean = num.replace(",", "")
            if clean not in allowed:
                violations.append(num)

    return {
        "result": "PASS" if not violations else "FAIL",
        "extracted_count": len(extracted),
        "violations": violations,
    }
