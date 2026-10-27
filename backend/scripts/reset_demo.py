"""Reset demo database script.

Deletes the local SQLite database file and re-seeds it with clean demo data.
Usage:
    python backend/scripts/reset_demo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import DEFAULT_DATABASE_PATH
from app.database import engine, initialize_database
from scripts.seed import seed_database


def reset_demo() -> None:
    # Dispose active engine connections
    engine.dispose()

    # Remove SQLite file and any journal/WAL files
    for ext in ("", "-wal", "-shm", "-journal"):
        db_file = Path(f"{DEFAULT_DATABASE_PATH}{ext}")
        if db_file.exists():
            try:
                db_file.unlink()
                print(f"Removed {db_file.name}")
            except OSError as error:
                print(f"Warning: could not remove {db_file.name}: {error}")

    # Re-initialize schema and seed initial data
    initialize_database()
    seed_database()
    print("Demo database successfully reset to clean seeded state.")


if __name__ == "__main__":
    reset_demo()

