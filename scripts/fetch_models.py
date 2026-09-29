"""Download offline model assets. Run ONCE with internet access."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"


def fetch_bge():
    print("Downloading BAAI/bge-small-en-v1.5 ...")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    dest = MODELS_DIR / "bge-small-en-v1.5"
    dest.mkdir(parents=True, exist_ok=True)
    model.save(str(dest))
    print(f"  Saved to {dest}")


def fetch_paddleocr():
    print("Downloading PaddleOCR models ...")
    dest = MODELS_DIR / "paddleocr"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        print(f"  PaddleOCR models cached (check ~/.paddleocr or {dest})")
    except ImportError:
        print("  WARNING: PaddleOCR not installed, skipping")
    except Exception as e:
        print(f"  WARNING: PaddleOCR download failed: {e}")


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    fetch_bge()
    fetch_paddleocr()
    print("\nAll models downloaded. You can now set HF_HUB_OFFLINE=1.")


if __name__ == "__main__":
    main()
