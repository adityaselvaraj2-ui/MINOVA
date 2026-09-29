from __future__ import annotations

import hashlib
import logging

import httpx

from app.config import settings
from app.services.factsheet import fact_sheet_to_prompt_block
from app.services.numberguard import guard_check

logger = logging.getLogger("minetrace.narration")

SYSTEM_PROMPT = (
    "You are a mining operations analyst writing factual reports for CMPDI/CIL. "
    "RULES:\n"
    "1. Use ONLY numbers from the FACT SHEET below. Do not compute new numbers.\n"
    "2. Separate facts from interpretation. Start with [RECORDED] section containing "
    "only factual statements. Then [INTERPRETATION] section with analysis.\n"
    "3. Tag each fact with its source: [F1], [F2], etc.\n"
    "4. Be concise. Use professional mining terminology.\n"
    "5. Never invent data or hallucinate numbers."
)


def _build_user_prompt(fact_sheet: dict) -> str:
    block = fact_sheet_to_prompt_block(fact_sheet)
    return (
        f"{block}\n\n"
        "Write a report description for the above data. "
        "Format:\n\n"
        "[RECORDED]\n"
        "Factual statements with [F1], [F2] tags.\n\n"
        "[INTERPRETATION]\n"
        "Analysis and observations."
    )


def _call_ollama(system: str, user: str, model: str) -> str | None:
    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {
                    "temperature": settings.ollama_temperature,
                    "seed": settings.ollama_seed,
                    "num_ctx": settings.ollama_num_ctx,
                },
            },
            timeout=120.0,
        )
        if resp.status_code == 200:
            return resp.json()["message"]["content"]
        logger.warning("Ollama returned %s", resp.status_code)
        return None
    except Exception:
        logger.exception("Ollama call failed")
        return None


def _split_sections(text: str) -> tuple[str, str]:
    recorded = ""
    interpretation = ""
    current = "recorded"

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("[RECORDED]"):
            current = "recorded"
            continue
        if stripped.upper().startswith("[INTERPRETATION]"):
            current = "interpretation"
            continue
        if current == "recorded":
            recorded += line + "\n"
        else:
            interpretation += line + "\n"

    return recorded.strip(), interpretation.strip()


def generate_description(
    fact_sheet: dict,
) -> dict:
    user_prompt = _build_user_prompt(fact_sheet)
    prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()

    model = settings.ollama_primary_model
    raw_text = _call_ollama(SYSTEM_PROMPT, user_prompt, model)

    if raw_text is None:
        model = settings.ollama_secondary_model
        raw_text = _call_ollama(SYSTEM_PROMPT, user_prompt, model)

    if raw_text is None:
        return _template_fallback(fact_sheet, prompt_hash)

    guard = guard_check(raw_text, fact_sheet)
    recorded, interpretation = _split_sections(raw_text)

    if guard["result"] == "FAIL":
        logger.warning(
            "Number guard FAIL: violations=%s, falling back to template",
            guard["violations"],
        )
        return _template_fallback(fact_sheet, prompt_hash)

    return {
        "text_recorded": recorded,
        "text_interpretation": interpretation,
        "model": model,
        "prompt_hash": prompt_hash,
        "guard_result": guard["result"],
        "source": "LLM",
    }


def _template_fallback(fact_sheet: dict, prompt_hash: str) -> dict:
    level = fact_sheet.get("report_level", "")
    period = fact_sheet.get("period_start", "")
    end = fact_sheet.get("period_end", "")
    prod = fact_sheet.get("production_t", "0")
    ob = fact_sheet.get("overburden_m3", "0")
    avail = fact_sheet.get("availability_pct", "0")
    sr = fact_sheet.get("stripping_ratio", "0")
    coverage = fact_sheet.get("coverage", "0/0")
    workers = fact_sheet.get("workers_present", 0)
    planned = fact_sheet.get("planned_min", 0)
    operating = fact_sheet.get("operating_min", 0)
    stoppage = fact_sheet.get("stoppage_min", 0)

    period_str = period if period == end else f"{period} to {end}"

    recorded = (
        f"[F1] {level} report for period {period_str}. "
        f"[F2] Total production: {prod} tonnes. "
        f"[F3] Total overburden removal: {ob} cubic metres. "
        f"[F4] Stripping ratio: {sr}. "
        f"[F5] Equipment availability: {avail}%. "
        f"[F6] Total planned time: {planned} minutes, "
        f"operating time: {operating} minutes, "
        f"stoppage: {stoppage} minutes. "
        f"[F7] Total workers deployed: {workers}. "
        f"[F8] Data coverage: {coverage} children present."
    )

    interpretation = (
        "Template-generated description. "
        "AI narration unavailable — all numbers above are deterministic "
        "and traceable to source shift entries via lineage."
    )

    return {
        "text_recorded": recorded,
        "text_interpretation": interpretation,
        "model": None,
        "prompt_hash": prompt_hash,
        "guard_result": "TEMPLATE",
        "source": "TEMPLATE_FALLBACK",
    }
