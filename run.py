"""FloorTrack AI — Unified One-Command Development Runner.

Starts both the FastAPI backend and the Vite frontend dev server concurrently.
Usage:
    python run.py
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)


def main() -> None:
    print("=" * 60)
    print("   FloorTrack AI — Hospital Asset Intelligence Prototype")
    print("=" * 60)
    print(f"Project root: {ROOT_DIR}")
    print(f"Python interpreter: {VENV_PYTHON}")

    # Step 1: Ensure database initialized and seeded
    print("\n[1/3] Initializing and seeding local SQLite database...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    subprocess.run(
        [str(VENV_PYTHON), "-c", "from app.database import initialize_database; from scripts.seed import seed_database; initialize_database(); seed_database()"],
        cwd=str(BACKEND_DIR),
        env=env,
        check=True,
    )

    # Step 2: Launch FastAPI backend
    print("\n[2/3] Launching FastAPI backend on http://127.0.0.1:8000...")
    backend_proc = subprocess.Popen(
        [
            str(VENV_PYTHON),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
    )

    # Step 3: Launch Vite frontend
    print("\n[3/3] Launching Vite frontend on http://localhost:5173...")
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=str(FRONTEND_DIR),
    )

    time.sleep(2)
    print("\n" + "=" * 60)
    print("   FloorTrack AI is running!")
    print("   - Web UI Dashboard:   http://localhost:5173")
    print("   - API & Swagger Docs: http://127.0.0.1:8000/docs")
    print("   - OpenAPI 3.1 Spec:   http://127.0.0.1:8000/openapi.json")
    print("=" * 60)
    print("Press Ctrl+C to stop all services.\n")

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("Backend terminated unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend terminated unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        for proc, name in ((backend_proc, "Backend"), (frontend_proc, "Frontend")):
            if proc.poll() is None:
                print(f"Terminating {name}...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("All services stopped.")


if __name__ == "__main__":
    main()

