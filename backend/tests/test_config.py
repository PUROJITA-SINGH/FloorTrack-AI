import importlib
import os
from pathlib import Path

import pytest


def test_env_example_loads_cleanly(monkeypatch) -> None:
    example_path = Path(__file__).resolve().parents[1] / ".env.example"
    assert example_path.exists(), "backend/.env.example must exist"

    # Parse key-value pairs from .env.example
    env_vars: dict[str, str] = {}
    for line in example_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if sep:
            env_vars[key.strip()] = val.strip()

    assert "DATABASE_URL" in env_vars
    assert "CONFIRMATION_WINDOW_HOURS" in env_vars

    # Apply environment variables
    for key, val in env_vars.items():
        monkeypatch.setenv(key, val)

    # Import/reload app.config and verify loaded settings
    import app.config

    reloaded = importlib.reload(app.config)
    assert reloaded.DATABASE_URL == env_vars["DATABASE_URL"]
    assert reloaded.CONFIRMATION_WINDOW_HOURS == 24.0
    assert reloaded.CONFIRMATION_WINDOW.total_seconds() == 24 * 3600


def test_invalid_confirmation_window_raises(monkeypatch) -> None:
    monkeypatch.setenv("CONFIRMATION_WINDOW_HOURS", "-1")
    import app.config

    with pytest.raises(ValueError, match="CONFIRMATION_WINDOW_HOURS must be greater than zero"):
        importlib.reload(app.config)

    # Restore clean state
    monkeypatch.setenv("CONFIRMATION_WINDOW_HOURS", "24")
    importlib.reload(app.config)

