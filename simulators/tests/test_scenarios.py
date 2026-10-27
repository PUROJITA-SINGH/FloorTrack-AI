from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from simulators import common
from simulators.ble import simulator as ble_simulator
from simulators.camera import simulator as camera_simulator
from simulators.run_scenario import SCENARIO_NAMES

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = {
    "assets": [
        {
            "id": f"00000000-0000-0000-0000-0000000000{number:02d}",
            "code": f"P-{number:03d}",
            "serial_number": f"SN-{number:03d}",
            "qr_code": f"QR-{number:03d}",
            "tags": [f"TAG-{number:03d}"],
        }
        for number in range(1, 10)
    ],
    "zones": [
        {"id": "00000000-0000-0000-0000-000000000010", "name": "Ward A"},
        {"id": "00000000-0000-0000-0000-000000000011", "name": "Ward B"},
    ],
    "cameras": [{"id": "00000000-0000-0000-0000-000000000020", "name": "CAM-1"}],
    "gateways": [
        {
            "id": f"00000000-0000-0000-0000-0000000000{number + 29:02d}",
            "name": f"GW-{number}",
            "x": x,
            "y": y,
        }
        for number, (x, y) in enumerate(((10, 10), (90, 10), (10, 90), (90, 90)), start=1)
    ],
}


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.posted: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, url: str) -> httpx.Response:
        return httpx.Response(200, json=TOPOLOGY, request=httpx.Request("GET", url))

    def post(self, url: str, json: dict) -> httpx.Response:
        self.posted.append((url, json))
        return httpx.Response(
            201,
            json={"status": "accepted"},
            request=httpx.Request("POST", url),
        )


def test_all_required_scenarios_have_recorded_expected_outputs() -> None:
    definitions = common.load_scenario_definitions()
    assert set(SCENARIO_NAMES) == {
        "normal_movement",
        "agreement",
        "camera_occlusion",
        "ble_signal_bleeding",
        "ble_tag_failure",
        "unknown_asset",
        "stale_gateway",
        "shortage_surge",
        "excess_inventory",
        "camera_silent",
        "status_never_confirmed",
    }
    assert all(
        isinstance(definitions[name].get("expected"), dict)
        and definitions[name].get("description")
        for name in SCENARIO_NAMES
    )
    assert "operational-status" not in (ROOT / "run_scenario.py").read_text(
        encoding="utf-8"
    )


def test_camera_simulator_posts_public_event_for_configured_zone(monkeypatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr(camera_simulator.httpx, "Client", lambda **kwargs: fake)

    event_ids = camera_simulator.run("agreement", base_url="http://test")

    assert len(event_ids) == 1
    url, payload = fake.posted[0]
    assert url == "http://test/api/v1/events/camera"
    assert payload["camera_id"] == TOPOLOGY["cameras"][0]["id"]
    assert payload["detections"][0]["asset_identifier"] == "TAG-002"
    assert payload["detections"][0]["zone_id"] == TOPOLOGY["zones"][0]["id"]


def test_ble_simulator_posts_gateway_batch_with_one_timestamp(monkeypatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr(ble_simulator.httpx, "Client", lambda **kwargs: fake)

    event_ids = ble_simulator.run("agreement", base_url="http://test")

    assert len(event_ids) == 1
    url, payload = fake.posted[0]
    assert url == "http://test/api/v1/events/ble"
    assert payload["tag_id"] == "TAG-002"
    assert len(payload["readings"]) == 2
    assert {reading["timestamp"] for reading in payload["readings"]} == {
        payload["timestamp"]
    }


def test_disabled_camera_silence_posts_no_negative_detection(monkeypatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr(camera_simulator.httpx, "Client", lambda **kwargs: fake)

    assert camera_simulator.run("camera_silent", base_url="http://test") == []
    assert fake.posted == []


def test_stale_event_timestamp_is_older_than_twenty_minutes() -> None:
    stale = datetime.fromisoformat(common.event_timestamp("now_minus_20m"))
    assert (datetime.now(UTC) - stale).total_seconds() >= 19 * 60
