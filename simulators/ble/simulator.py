from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

from simulators.common import (
    API_BASE_URL,
    find_asset,
    find_named,
    get_topology,
    load_scenario,
    post_payload,
    scenario_timestamp,
)


def run(
    scenario_name: str,
    delay: float = 0.0,
    base_url: str = API_BASE_URL,
) -> list[str]:
    scenario = load_scenario("ble", scenario_name)
    if not scenario.get("enabled", True):
        print(f"BLE simulator disabled for {scenario_name}")
        return []
    if delay < 0:
        raise ValueError("delay must be zero or greater")

    with httpx.Client(timeout=15.0) as client:
        topology = get_topology(client, base_url)
        asset = find_asset(topology, scenario["asset_code"]) if scenario.get("asset_code") else None
        tag_id = scenario.get("tag_id")
        if tag_id is None and asset is not None:
            tags = asset.get("tags", [])
            tag_id = tags[0] if tags else None
        if tag_id is None:
            raise ValueError("BLE scenario needs a tag_id or a resolvable asset with a tag")

        events = scenario.get("events", [{}])
        if not isinstance(events, list):
            raise ValueError("BLE scenario events must be an array")
        event_ids: list[str] = []
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                raise ValueError("each BLE scenario event must be an object")
            timestamp = scenario_timestamp(event)
            readings = []
            for reading in event.get("readings", scenario.get("readings", [])):
                if not isinstance(reading, dict):
                    raise ValueError("each BLE reading must be an object")
                gateway = find_named(topology, "gateways", reading["gateway_name"])
                readings.append(
                    {
                        "gateway_id": gateway["id"],
                        "rssi": reading["rssi"],
                        "timestamp": timestamp,
                    }
                )
            payload = {
                "tag_id": tag_id,
                "event_id": f"sim-ble-{scenario_name}-{uuid.uuid4()}",
                "timestamp": timestamp,
                "readings": readings,
            }
            post_payload(client, base_url, "/api/v1/events/ble", payload)
            event_ids.append(payload["event_id"])
            if index < len(events) - 1:
                time.sleep(delay)
        return event_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Post simulated BLE events")
    parser.add_argument("--scenario", required=True, help="Scenario name")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between events in seconds")
    parser.add_argument("--base-url", default=API_BASE_URL)
    args = parser.parse_args()
    run(args.scenario, args.delay, args.base_url.rstrip("/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
