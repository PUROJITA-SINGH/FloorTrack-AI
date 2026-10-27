from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulators.ble.simulator import run as run_ble
from simulators.camera.simulator import run as run_camera
from simulators.common import (
    API_BASE_URL,
    find_asset,
    find_named,
    get_topology,
    load_scenario_definitions,
)
from simulators.heartbeat.simulator import run as run_heartbeat

SCENARIO_NAMES = tuple(load_scenario_definitions())


def _get_json(
    client: httpx.Client,
    base_url: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
) -> Any:
    response = client.get(f"{base_url}{path}", params=params)
    response.raise_for_status()
    return response.json()


def _post_json(
    client: httpx.Client,
    base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    params: dict[str, str] | None = None,
) -> Any:
    response = client.post(f"{base_url}{path}", json=payload, params=params)
    response.raise_for_status()
    result = response.json()
    print(f"{path}: HTTP {response.status_code} {result}")
    return result


def _zone_name(topology: dict[str, Any], zone_id: str | None) -> str | None:
    if zone_id is None:
        return None
    return next(
        (
            zone["name"]
            for zone in topology["zones"]
            if zone["id"] == zone_id
        ),
        None,
    )


def _assert_expected(
    scenario_name: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> None:
    mismatches = {
        key: {"expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    }
    print(f"{scenario_name} expected: {json.dumps(expected, sort_keys=True)}")
    print(f"{scenario_name} actual:   {json.dumps(actual, sort_keys=True)}")
    if mismatches:
        raise RuntimeError(
            f"Scenario {scenario_name!r} did not match its expected output: "
            f"{json.dumps(mismatches, sort_keys=True)}"
        )


def run_scenario(
    scenario_name: str,
    delay: float = 0.0,
    base_url: str = API_BASE_URL,
) -> dict[str, Any]:
    definitions = load_scenario_definitions()
    if scenario_name not in definitions:
        raise ValueError(
            f"Unknown scenario {scenario_name!r}; choose from {', '.join(definitions)}"
        )
    if delay < 0:
        raise ValueError("delay must be zero or greater")
    base_url = base_url.rstrip("/")
    definition = definitions[scenario_name]
    expected = definition["expected"]

    with httpx.Client(timeout=30.0) as client:
        topology = get_topology(client, base_url)
        camera_config = definition.get("camera", {"enabled": False})
        ble_config = definition.get("ble", {"enabled": False})
        camera_event_ids = (
            run_camera(scenario_name, delay, base_url)
            if camera_config.get("enabled", False)
            else []
        )
        ble_event_ids = (
            run_ble(scenario_name, delay, base_url)
            if ble_config.get("enabled", False)
            else []
        )
        heartbeat_config = definition.get("heartbeat", {"enabled": False})
        if heartbeat_config.get("enabled", False):
            run_heartbeat(scenario_name, base_url)

        actual: dict[str, Any]
        unknown_asset = scenario_name == "unknown_asset"
        if unknown_asset:
            event = _get_json(
                client,
                base_url,
                f"/api/v1/events/{camera_event_ids[0]}",
            )
            actual = {
                "unknown_asset": event["unknown_asset"],
                "asset_id": event["asset_id"],
                "asset_state_created": event["asset_id"] is not None,
            }
        elif scenario_name == "shortage_surge":
            demand_config = definition["demand"]
            zone = find_named(topology, "zones", demand_config["zone_name"])
            asset = find_asset(topology, demand_config["asset_code"])
            asset_detail = _get_json(
                client,
                base_url,
                f"/api/v1/assets/{asset['id']}",
            )
            filters = {
                "zone_id": zone["id"],
                "asset_type_id": asset_detail["asset_type_id"],
                "horizon_days": "7",
            }
            forecast_before = _get_json(
                client,
                base_url,
                "/api/v1/forecast",
                params=filters,
            )
            target_demand = int(demand_config["target_demand"])
            additional_demand = max(
                0,
                target_demand - forecast_before["demand"],
            )
            if additional_demand:
                _post_json(
                    client,
                    base_url,
                    "/api/v1/events/demand",
                    {
                        "zone_id": zone["id"],
                        "asset_type_id": asset_detail["asset_type_id"],
                        "demand_count": additional_demand,
                        "event_date": date.today().isoformat(),
                    },
                )
            forecast = _get_json(
                client,
                base_url,
                "/api/v1/forecast",
                params=filters,
            )
            actual = {
                "demand": forecast["demand"],
                "demand_at_least": (
                    expected["demand_at_least"]
                    if forecast["demand"] >= expected["demand_at_least"]
                    else forecast["demand"]
                ),
                "band": forecast["band"],
                "demand_and_usable_supply_reported": (
                    "demand" in forecast and "projected_usable" in forecast
                ),
            }
        elif scenario_name == "excess_inventory":
            assets_before = _get_json(client, base_url, "/api/v1/assets")
            recommendations = _get_json(
                client,
                base_url,
                "/api/v1/inventory/recommendations",
            )
            assets_after = _get_json(client, base_url, "/api/v1/assets")
            statuses_before = {
                asset["id"]: asset["operational_status"]
                for asset in assets_before
            }
            statuses_after = {
                asset["id"]: asset["operational_status"]
                for asset in assets_after
            }
            actual = {
                "availability_unchanged": statuses_before == statuses_after,
                "recommendations_are_drafts": all(
                    item["status"] == "draft"
                    and item["requires_human_confirmation"] is True
                    for item in recommendations
                ),
                "recommendation_count": len(recommendations),
            }
        elif scenario_name == "status_never_confirmed":
            asset = find_asset(topology, definition["asset_code"])
            _post_json(
                client,
                base_url,
                "/api/v1/fusion/run",
                {},
                params={"asset_id": asset["id"]},
            )
            detail = _get_json(client, base_url, f"/api/v1/assets/{asset['id']}")
            assets = _get_json(client, base_url, "/api/v1/assets")
            inventory = _get_json(client, base_url, "/api/v1/inventory")
            status_history = _get_json(
                client,
                base_url,
                f"/api/v1/assets/{asset['id']}/status-history",
            )
            zone_name = detail["zone"]
            row = next(
                (
                    row
                    for row in inventory
                    if row["zone_name"] == zone_name
                    and row["asset_type_name"] == detail["asset_type_name"]
                ),
                None,
            )
            api_usable_count = sum(
                1
                for listed in assets
                if listed.get("zone") == zone_name
                and listed.get("asset_type_name") == detail["asset_type_name"]
                and listed.get("operational_status") == "available"
            )
            actual = {
                "operational_status": detail["operational_status"],
                "usable_count_excludes_asset": (
                    row is not None
                    and row["usable_count"] == api_usable_count
                ),
                "status_write_made": len(status_history) > 0,
            }
        else:
            asset_code = (
                definition.get("asset_code")
                or camera_config.get("asset_code")
                or ble_config.get("asset_code")
            )
            asset = find_asset(topology, asset_code)
            before = _get_json(client, base_url, f"/api/v1/assets/{asset['id']}")
            fusion_body = _post_json(
                client,
                base_url,
                "/api/v1/fusion/run",
                {},
                params={"asset_id": asset["id"]},
            )
            result = fusion_body["results"][0]
            after = _get_json(client, base_url, f"/api/v1/assets/{asset['id']}")

            if scenario_name == "camera_silent":
                actual = {
                    "status": result["status"],
                    "state_changed": result["state_changed"],
                    "location_confidence_and_availability_unchanged": all(
                        before.get(key) == after.get(key)
                        for key in (
                            "zone_id",
                            "confidence_band",
                            "decision_status",
                            "operational_status",
                            "status_source",
                        )
                    ),
                }
            elif scenario_name in {"agreement", "normal_movement"}:
                actual = {
                    "decision_status": result["decision_status"],
                    "zone_name": _zone_name(topology, result.get("zone_id")),
                    "camera_and_ble_agree": (
                        result.get("camera_zone_id") == result.get("ble_zone_id")
                    ),
                }
            elif scenario_name == "camera_occlusion":
                actual = {
                    "decision_status": result["decision_status"],
                    "zone_name": _zone_name(topology, result.get("zone_id")),
                    "camera_zone_id": result.get("camera_zone_id"),
                    "ble_zone_present": result.get("ble_zone_id") is not None,
                }
            elif scenario_name == "ble_signal_bleeding":
                review_alerts = _get_json(
                    client,
                    base_url,
                    "/api/v1/alerts",
                    params={"status": "open"},
                )
                actual = {
                    "decision_status": result["decision_status"],
                    "review_state": result.get("review_state"),
                    "camera_zone_name": _zone_name(
                        topology,
                        result.get("camera_zone_id"),
                    ),
                    "ble_zone_name": _zone_name(topology, result.get("ble_zone_id")),
                    "review_alert_required": result.get("review_alert_id") is not None
                    and any(
                        alert["id"] == result["review_alert_id"]
                        for alert in review_alerts
                    ),
                }
            elif scenario_name == "ble_tag_failure":
                actual = {
                    "decision_status": result["decision_status"],
                    "zone_name": _zone_name(topology, result.get("zone_id")),
                    "gateway_count": result["gateway_count"],
                    "availability_unchanged": (
                        before["operational_status"] == after["operational_status"]
                        and before["status_source"] == after["status_source"]
                    ),
                }
            elif scenario_name == "stale_gateway":
                actual = {
                    "decision_status": result["decision_status"],
                    "confidence_band": result["confidence_band"],
                    "gateway_count": result["gateway_count"],
                }
            else:
                raise ValueError(f"No verifier for scenario {scenario_name!r}")

        _assert_expected(scenario_name, expected, actual)
        return actual


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a FloorTrack scenario using public HTTP API endpoints"
    )
    parser.add_argument("--scenario", required=True, choices=SCENARIO_NAMES)
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay in seconds between events from a sensor simulator",
    )
    parser.add_argument("--base-url", default=API_BASE_URL)
    args = parser.parse_args()
    run_scenario(args.scenario, args.delay, args.base_url)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (httpx.HTTPError, OSError, ValueError, RuntimeError) as error:
        print(f"Scenario failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
