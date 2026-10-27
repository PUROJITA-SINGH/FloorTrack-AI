from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

SIMULATORS_DIR = Path(__file__).resolve().parent
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def load_scenario(component: str, name: str) -> dict[str, Any]:
    definitions = load_scenario_definitions()
    scenario = definitions.get(name)
    if not isinstance(scenario, dict):
        raise ValueError(f"Unknown scenario {name!r}")
    component_config = scenario.get(component, {"enabled": False})
    if not isinstance(component_config, dict):
        raise ValueError(f"Scenario {name!r} has invalid {component} configuration")
    return component_config


def load_scenario_definitions() -> dict[str, Any]:
    path = SIMULATORS_DIR / "scenarios" / "definitions.json"
    with path.open(encoding="utf-8") as scenario_file:
        data = json.load(scenario_file)
    if not isinstance(data, dict):
        raise ValueError(f"Scenario must be a JSON object: {path}")
    return data


def get_topology(client: httpx.Client, base_url: str) -> dict[str, Any]:
    response = client.get(f"{base_url}/api/v1/simulator/topology")
    response.raise_for_status()
    topology = response.json()
    if not isinstance(topology, dict):
        raise ValueError("Simulator topology endpoint must return a JSON object")
    return topology


def find_named(
    topology: dict[str, Any],
    collection: str,
    name: str,
) -> dict[str, Any]:
    entries = topology.get(collection)
    if not isinstance(entries, list):
        raise ValueError(f"Simulator topology has no {collection} list")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    raise ValueError(f"Could not find {collection[:-1]} named {name!r}")


def find_asset(topology: dict[str, Any], code: str) -> dict[str, Any]:
    assets = topology.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, dict) and asset.get("code") == code:
                return asset
    raise ValueError(f"Could not find asset with code {code!r}")


def event_timestamp(value: str | None = None) -> str:
    if value in (None, "", "now"):
        return datetime.now(UTC).isoformat()
    if value == "now_minus_20m":
        return (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
    return value


def scenario_timestamp(item: dict[str, Any]) -> str:
    return event_timestamp(item.get("timestamp"))


def post_payload(
    client: httpx.Client,
    base_url: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(f"{base_url}{path}", json=payload)
    response.raise_for_status()
    body = response.json()
    print(f"{path}: HTTP {response.status_code} {body}")
    return body
