"""Text-to-SQL over the MineTrace relational store (SQLite).

Ported from teammate architecture (cmpdi-ai-reporting-platform), adapted:
- LLM generates SQL from a STRICT schema whitelist
- Injection guard: single SELECT statement, blocklisted keywords, no comments
- Readonly execution with row cap; narration by the same local LLM
- Graceful degradation: returns the SQL + raw rows, or an error - never writes
"""
from __future__ import annotations

import logging
import re
import time

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import User
from app.services.llm.gateway import chat

logger = logging.getLogger("minetrace.text_to_sql")

ROW_CAP = 100
TIMEOUT_S = 5
LLM_TIMEOUT_S = 180.0  # qwen3:8b cold-load can exceed 2 minutes

SCHEMA_HINT = """Tables and columns (SQLite):
- report(id, uuid, level[DAILY|WEEKLY|MONTHLY|QUARTERLY|HALF_YEARLY|ANNUAL],
  mine_id, bench_id, period_start, period_end, status, version,
  expected_children, present_children)
- report_metric(id, report_id, metric_code[production_milli_t|ob_milli_m3|
  planned_min|operating_min|stoppage_min|workers_present|
  stripping_ratio_x1000|availability_bp], value_int, unit, is_additive)
- shift_entry(id, mine_id, bench_id, work_date, shift_code[A|B|C],
  planned_min, workers_present, production_milli_t, ob_milli_m3,
  stoppage_min, operating_min, status, version)
- mine(id, code, name, subsidiary_id, sector_id)
- bench(id, mine_id, code, name, bench_type)
- document(id, filename, file_type, page_count, status, uploaded_at)
- document_chunk(id, document_id, chunk_index, text, page_number)
Notes: *_milli_* values are stored x1000 (milli-units). Dates are ISO strings.
Status and level columns store UPPERCASE values (e.g. 'READY', 'APPROVED',
'DAILY') - match them with uppercase literals.
Rules: SQLite dialect. Exactly ONE statement. SELECT only. Always include a
LIMIT (max {cap}).
"""

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|"
    r"VACUUM|REINDEX|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)\b",
    re.IGNORECASE,
)


def _is_safe_sql(sql: str) -> bool:
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        return False                      # single statement only
    if "--" in stripped or "/*" in stripped:
        return False                      # no comments
    if not re.match(r"(?is)^\s*SELECT\s", stripped):
        return False
    return not FORBIDDEN.search(stripped)


def _tables_in_sql(sql: str) -> set[str]:
    """Extract table names after FROM / JOIN for allow-list checking."""
    return set(
        m.lower()
        for m in re.findall(
            r"(?is)\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql
        )
    )


def _llm_sql(question: str) -> str | None:
    system = (
        "You are an expert SQLite query writer. Given a schema and a question, "
        "output ONLY one SQLite SELECT statement. No explanations, no markdown, "
        "no comments, no semicolons at the end."
    )
    user = f"{SCHEMA_HINT.format(cap=ROW_CAP)}\nQuestion: {question}\nSELECT "
    try:
        raw, _model = chat(system, user, timeout=LLM_TIMEOUT_S, max_tokens=256)
        if raw is None:
            return None
        raw = re.sub(r"^```(?:sql)?|```$", "", raw, flags=re.IGNORECASE).strip()
        if not raw.upper().startswith("SELECT"):
            raw = "SELECT " + raw
        return raw.rstrip(";")
    except Exception:
        logger.exception("LLM SQL generation failed")
        return None


def _llm_narrate(question: str, columns: list[str], rows: list) -> str | None:
    table = "\n".join(
        " | ".join(str(v) for v in row) for row in rows[:25]
    )
    system = (
        "You are a mining data analyst. Narrate the SQL result for the user's "
        "question in 1-3 sentences. Use ONLY numbers from the result table. "
        "Do not compute new aggregates beyond simple reading."
    )
    user = f"Question: {question}\nColumns: {', '.join(columns)}\nRows:\n{table}\nAnswer:"
    try:
        answer, _model = chat(system, user, timeout=LLM_TIMEOUT_S, max_tokens=512)
        return answer
    except Exception:
        logger.exception("LLM narration failed")
        return None


def run_text_to_sql(
    db: Session, question: str,
    user: User | None = None,
) -> dict:
    started = time.time()
    sql = _llm_sql(question)
    if sql is None:
        return {"ok": False, "error": "LLM unavailable for SQL generation",
                "sql": None, "columns": [], "rows": [], "narrative": None}

    if not _is_safe_sql(sql):
        return {"ok": False, "error": "Generated SQL failed the safety guard",
                "sql": sql, "columns": [], "rows": [], "narrative": None}

    # Table allow-list (defense in depth beyond the keyword guard)
    tables = _tables_in_sql(sql)
    disallowed = tables - set(settings.sql_allow_tables)
    if disallowed:
        return {
            "ok": False,
            "error": f"SQL references non-allowed tables: {sorted(disallowed)}",
            "sql": sql, "columns": [], "rows": [], "narrative": None,
        }

    if re.search(r"(?i)\bLIMIT\s+\d+", sql) is None:
        sql = f"{sql} LIMIT {ROW_CAP}"

    # Subsidiary scoping is injected IN CODE, not via the prompt (constraint):
    # wrap the generated SELECT as a subquery over an additionally filtered
    # mine set. For users bound to a subsidiary's mines, add mine_id filter.
    scoped_sql = sql
    scoped_note = None
    if user is not None:
        mine_ids = _scoped_mine_ids(db, user)
        if mine_ids is not None:
            id_list = ",".join(str(m) for m in mine_ids) or "-1"
            scoped_sql = (
                f"SELECT * FROM ({sql.rstrip(';')}) WHERE mine_id IS NULL "
                f"OR mine_id IN ({id_list})"
            )
            scoped_note = f"scoped to {len(mine_ids)} mine(s)"

    raw = sql_text(scoped_sql)
    try:
        result = db.execute(raw)
        columns = list(result.keys())
        rows = [list(r) for r in result.fetchmany(ROW_CAP)]
    except Exception as exc:
        return {"ok": False, "error": f"SQL execution error: {exc}",
                "sql": scoped_sql, "columns": [], "rows": [], "narrative": None}

    if not rows:
        # Empty result set: the LLM must never narrate (it invents numbers).
        narrative = (
            "No matching records for this period/scope. "
            "Check the date range or ask about a different period."
        )
    else:
        narrative = _llm_narrate(question, columns, rows)
    return {
        "ok": True,
        "sql": scoped_sql,
        "columns": columns,
        "rows": rows,
        "narrative": narrative,
        "elapsed_ms": int((time.time() - started) * 1000),
        "row_count": len(rows),
        "scope": scoped_note,
    }


def _scoped_mine_ids(db: Session, user) -> list[int] | None:
    """Mine IDs the user may see. None = unrestricted (HQ roles)."""
    from app.db.models import Mine

    q = db.query(Mine.id)
    if user.mine_id is not None:
        return [user.mine_id]
    # users with a departmental HQ role but no mine binding: restrict by
    # subsidiary when the role rank is low (field-adjacent roles)
    if getattr(user, "role", None) and user.role.rank <= 2:
        rows = q.all()
        return [r[0] for r in rows]
    return None
