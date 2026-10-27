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
    scenario = load_scenario("camera", scenario_name)
    if not scenario.get("enabled", True):
        print(f"camera simulator disabled for {scenario_name}")
        return []
    if delay < 0:
        raise ValueError("delay must be zero or greater")

    with httpx.Client(timeout=15.0) as client:
        topology = get_topology(client, base_url)
        camera = find_named(topology, "cameras", scenario["camera_name"])
        asset_code = scenario.get("asset_code")
        asset = find_asset(topology, asset_code) if asset_code else None
        default_zone_name = scenario.get("zone_name")

        events = scenario.get("events", [{}])
        if not isinstance(events, list):
            raise ValueError("camera scenario events must be an array")
        event_ids: list[str] = []
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                raise ValueError("each camera scenario event must be an object")
            identifier = scenario.get("asset_identifier")
            if identifier is None and asset is not None:
                tags = asset.get("tags", [])
                identifier = tags[0] if tags else asset.get("serial_number")
            if identifier is None:
                raise ValueError("camera scenario needs an asset_identifier or a resolvable asset")

            detection = {
                "asset_identifier": identifier,
                "confidence": event.get("confidence", scenario.get("confidence", 0.9)),
                "zone_id": find_named(
                    topology,
                    "zones",
                    event.get("zone_name", default_zone_name),
                )["id"],
            }
            if asset is not None and scenario.get("include_serial_number", False):
                detection["serial_number"] = asset.get("serial_number")

            payload = {
                "camera_id": camera["id"],
                "event_id": f"sim-camera-{scenario_name}-{uuid.uuid4()}",
                "timestamp": scenario_timestamp(event),
                "detections": [detection],
            }
            post_payload(client, base_url, "/api/v1/events/camera", payload)
            event_ids.append(payload["event_id"])
            if index < len(events) - 1:
                time.sleep(delay)
        return event_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Post simulated camera events")
    parser.add_argument("--scenario", required=True, help="Scenario name")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between events in seconds")
    parser.add_argument("--base-url", default=API_BASE_URL)
    args = parser.parse_args()
    run(args.scenario, args.delay, args.base_url.rstrip("/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
