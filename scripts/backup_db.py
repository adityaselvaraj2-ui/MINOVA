"""SQLite backup: online VACUUM INTO copy + zip of exports.

Usage: python scripts/backup_db.py [--dest DIR]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(PROJECT_ROOT / "backups"))
    args = ap.parse_args()
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from app.config import settings

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_backup = dest / f"minetrace_{stamp}.db"
    db_path = settings.db_path

    if not db_path.exists():
        print(f"DB not found at {db_path}")
        raise SystemExit(1)

    # Online backup via sqlite3 CLI if available, else python
    try:
        subprocess.run(
            ["sqlite3", str(db_path), f".backup '{db_backup}'"], check=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        import sqlite3

        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(db_backup))
        src.backup(dst)
        dst.close()
        src.close()

    exports = settings.exports_path
    zip_path = dest / f"exports_{stamp}.zip"
    if exports.exists() and any(exports.iterdir()):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in exports.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(exports))

    print(f"Backup complete: {db_backup}")
    if zip_path.exists():
        print(f"Exports archived: {zip_path}")


if __name__ == "__main__":
    main()
