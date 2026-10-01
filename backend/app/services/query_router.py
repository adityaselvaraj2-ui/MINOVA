"""Query router (abstract commitment): decide per question whether it needs
structured DB lookup, document retrieval, or both, then answer accordingly.

Heuristic + LLM assistance, deterministic fallback:
- explicit numbers/period words ("production", "tonnes", month names, "mine")
  -> structured (Text-to-SQL)
- why/how/history/causes words -> documents (RAG)
- ambiguous -> BOTH (structured facts + cited passages)
The router never computes numbers itself; it only picks the lane(s).
"""
from __future__ import annotations

import re

STRUCTURED_HINTS = re.compile(
    r"(?i)\b(production|tonnes?t?\b|output|overburden|ob\b|availability|"
    r"stripping|workers|downtime|hours|minutes|target|achievement|"
    r"sum|total|average|average|count|how much|how many|"
    r"january|february|march|april|may|june|july|august|september|"
    r"october|november|december|month|week|quarter|annual|year)\b"
)
DOC_HINTS = re.compile(
    r"(?i)\b(why|reason|cause|explain|history|historical|document|report on|"
    r"summarise|summarize|describe|context|background|incident|"
    r"\u0915\u094d\u092f\u094b\u0902|\u0915\u093e\u0930\u0923)\b"  # Hindi: why / cause
)


def route_query(question: str) -> dict:
    wants_sql = bool(STRUCTURED_HINTS.search(question))
    wants_docs = bool(DOC_HINTS.search(question))
    if not wants_sql and not wants_docs:
        # default: try both so vague questions still get a useful answer
        wants_sql = wants_docs = True
    return {
        "structured": wants_sql,
        "documents": wants_docs,
        "mode": (
            "both" if wants_sql and wants_docs
            else "structured" if wants_sql
            else "documents"
        ),
    }
