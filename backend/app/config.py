import os
from datetime import timedelta
from pathlib import Path

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "floortrack.db"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
CONFIRMATION_WINDOW_HOURS = float(os.getenv("CONFIRMATION_WINDOW_HOURS", "24"))

if CONFIRMATION_WINDOW_HOURS <= 0:
    raise ValueError("CONFIRMATION_WINDOW_HOURS must be greater than zero")

CONFIRMATION_WINDOW = timedelta(hours=CONFIRMATION_WINDOW_HOURS)
