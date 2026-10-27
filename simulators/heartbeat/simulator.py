from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

from simulators.common import API_BASE_URL, find_named, get_topology, load_scenario, post_payload
from simulators.common import event_timestamp


def run(
    scenario_name: str,
    base_url: str = API_BASE_URL,
) -> None:
    scenario = load_scenario("heartbeat", scenario_name)
    if not scenario.get("enabled", True):
        print(f"heartbeat simulator disabled for {scenario_name}")
        return

    interval = float(scenario.get("interval_seconds", 5))
    duration = float(scenario.get("duration_seconds", 10))
    offline_after = scenario.get("offline_after_seconds")
    if interval <= 0 or duration < 0:
        raise ValueError("heartbeat interval must be positive and duration cannot be negative")
    if offline_after is not None and float(offline_after) < 0:
        raise ValueError("offline_after_seconds cannot be negative")
    if scenario["sensor_type"] not in {"camera", "gateway"}:
        raise ValueError("sensor_type must be 'camera' or 'gateway'")

    with httpx.Client(timeout=15.0) as client:
        topology = get_topology(client, base_url)
        collection = "cameras" if scenario["sensor_type"] == "camera" else "gateways"
        sensor = find_named(topology, collection, scenario["sensor_name"])

        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            if elapsed > duration:
                break
            if offline_after is not None and elapsed >= float(offline_after):
                print(f"{sensor['name']} simulated offline: stopped sending heartbeats")
                break

            post_payload(
                client,
                base_url,
                f"/api/v1/sensors/{sensor['id']}/heartbeat",
                {"timestamp": event_timestamp()},
            )
            sleep_for = min(interval, max(0.0, duration - (time.monotonic() - started)))
            if sleep_for <= 0:
                break
            time.sleep(sleep_for)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send simulated sensor heartbeats")
    parser.add_argument("--scenario", required=True, help="Scenario name")
    parser.add_argument("--base-url", default=API_BASE_URL)
    args = parser.parse_args()
    run(args.scenario, args.base_url.rstrip("/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
