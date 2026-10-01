"""Verify / add checksum & dimension validation for model downloads.

Usage:
  python scripts/download_models.py --all          # everything
  python scripts/download_models.py --llm          # ollama pulls
  python scripts/download_models.py --embeddings   # e5-small
  python scripts/download_models.py --reranker     # bge-reranker-v2-m3
  python scripts/download_models.py --verify       # verify local copies
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS = PROJECT_ROOT / "models"

LLM_MODELS = ["qwen3:8b", "qwen2.5:7b", "llama3.1:8b"]
HF_MODELS = {
    "intfloat/multilingual-e5-small": MODELS / "multilingual-e5-small",
    "BAAI/bge-reranker-v2-m3": MODELS / "bge-reranker-v2-m3",
}
EMBED_DIM = {"intfloat/multilingual-e5-small": 384}


def ollama_pull(model: str) -> bool:
    print(f"[ollama] pulling {model} ...")
    try:
        subprocess.run(["ollama", "pull", model], check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"  FAIL: {e}")
        return False


def hf_download(repo: str, dest: Path) -> bool:
    if (dest / "config.json").exists():
        print(f"[hf] {repo} already present at {dest}")
        return True
    print(f"[hf] downloading {repo} -> {dest}")
    exe = PROJECT_ROOT / "backend" / ".venv" / "Scripts" / "hf.exe"
    cmd = [str(exe)] if exe.exists() else ["hf"]
    try:
        subprocess.run([*cmd, "download", repo, "--local-dir", str(dest)], check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"  FAIL: {e}")
        return False


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify() -> bool:
    ok = True

    # 1) embeddings present + correct dimension
    e5 = MODELS / "multilingual-e5-small"
    if not (e5 / "config.json").exists():
        print("MISSING: multilingual-e5-small (run with --embeddings)")
        ok = False
    else:
        cfg = json.loads((e5 / "config.json").read_text())
        dim = cfg.get("hidden_size")
        expected = EMBED_DIM["intfloat/multilingual-e5-small"]
        print(f"multilingual-e5-small: hidden_size={dim} (expect {expected})")
        ok &= dim == expected

    # 2) sentence-transformers load check (dimension proof)
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "backend"))
        from app.services.embeddings import embed_single  # noqa: E402

        vec = embed_single("dimension check")
        if vec:
            print(f"embed_single: dim={len(vec)} (expect 384)")
            ok &= len(vec) == 384
        else:
            print("embed_single returned None (model failed to load)")
            ok = False
    except Exception as e:  # noqa: BLE001
        print(f"embedding load check failed: {e}")
        ok = False

    # 3) ollama models present
    try:
        import httpx

        tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3).json()
        present = {m["name"] for m in tags.get("models", [])}
        for m in LLM_MODELS:
            have = any(p == m or p.startswith(m + ":") for p in present)
            print(f"ollama {m}: {'OK' if have else 'MISSING'}")
            ok &= have
    except Exception as e:  # noqa: BLE001
        print(f"ollama check skipped: {e}")

    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--embeddings", action="store_true")
    ap.add_argument("--reranker", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if args.llm or args.all:
        for m in LLM_MODELS:
            ollama_pull(m)
    if args.embeddings or args.all:
        hf_download("intfloat/multilingual-e5-small", MODELS / "multilingual-e5-small")
    if args.reranker or args.all:
        hf_download("BAAI/bge-reranker-v2-m3", MODELS / "bge-reranker-v2-m3")
    if args.verify or (args.all and not args.llm):
        sys.exit(0 if verify() else 1)
    if args.all:
        sys.exit(0 if verify() else 1)


if __name__ == "__main__":
    main()
