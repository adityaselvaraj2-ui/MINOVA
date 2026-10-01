"""Light RAG eval harness: golden Q/A CSV -> retrieval hit-rate + grounded_pct.

CSV columns: question,answer,expect_file_substring
Usage: python scripts/eval_rag.py golden.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    golden_path = Path(sys.argv[1])
    from app.db.session import get_session_factory
    from app.services.rag import generate_cited_answer, grounded_pct, retrieve

    factory = get_session_factory()
    db = factory()

    rows = list(csv.DictReader(golden_path.open(encoding="utf-8")))
    hits = 0
    grounded_scores = []
    for r in rows:
        contexts = retrieve(db, r["question"])
        top_files = " ".join(c["filename"].lower() for c in contexts[:5])
        hit = r["expect_file_substring"].lower() in top_files
        hits += int(hit)
        result = generate_cited_answer(r["question"], contexts)
        gp = result.get("grounded_pct", grounded_pct(result.get("answer", ""), contexts))
        grounded_scores.append(gp)
        print(
            f"{'HIT ' if hit else 'MISS'} gp={gp:3d}%  {r['question'][:60]}"
        )

    n = len(rows) or 1
    print(f"\nRetrieval hit-rate: {hits}/{len(rows)} = {100*hits/n:.0f}%")
    print(f"Mean grounded_pct:  {sum(grounded_scores)/n:.1f}%")


if __name__ == "__main__":
    main()
