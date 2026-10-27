import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite://"

import pytest

from app.database import Base, engine, initialize_database
import app.models  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_sqlite_schema():
    Base.metadata.drop_all(bind=engine)
    initialize_database()
    yield
    Base.metadata.drop_all(bind=engine)
