from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import Asset, AssetType, Camera, CameraEvent, Facility, Floor, Tag, Zone
from app.routers.events import CameraDetection
from app.services.identity import resolve_asset, resolve_from_ble, resolve_from_camera


@pytest.fixture
def camera_event_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Session, Camera, Asset, Zone]]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    facility = Facility(name="Camera event test facility")
    session.add(facility)
    session.flush()
    floor = Floor(facility_id=facility.id, name="Test floor", floor_number=1)
    asset_type = AssetType(name="Test pump")
    session.add_all([floor, asset_type])
    session.flush()
    zone = Zone(
        floor_id=floor.id,
        name="Test zone",
        zone_type="ward",
        polygon_json=[[0, 0], [1, 0], [1, 1], [0, 1]],
    )
    session.add(zone)
    session.flush()
    asset = Asset(
        code="CAMERA-EVENT-TEST",
        serial_number="TEST-SERIAL",
        qr_code="TEST-QR",
        asset_type_id=asset_type.id,
        floor_id=floor.id,
        operational_status="status_unknown",
        status_source="workflow_adapter",
        status_actor="test",
        status_reason="test setup",
    )
    camera = Camera(
        floor_id=floor.id,
        name="Test camera",
        coverage_zone_ids=[],
        heartbeat_timeout_s=60,
        status="online",
    )
    session.add_all([asset, camera])
    session.flush()
    session.add(Tag(asset_id=asset.id, tag_type="ble", tag_value="CAMERA-EVENT-TAG"))
    session.flush()

    def override_get_db() -> Iterator[Session]:
        yield session

    from app.routers import events

    monkeypatch.setattr(events, "_run_fusion_in_background", lambda _asset_id: None)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, session, camera, asset, zone
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.close()
        session.close()
        transaction.rollback()
        connection.close()


def test_identity_resolvers_support_tag_serial_and_qr(
    camera_event_client: tuple[TestClient, Session, Camera, Asset, Zone],
) -> None:
    _, session, _, asset, _ = camera_event_client

    assert resolve_asset("CAMERA-EVENT-TAG", "tag", session) == asset
    assert resolve_asset("TEST-SERIAL", "serial", session) == asset
    assert resolve_asset("TEST-QR", "qr", session) == asset
    assert resolve_from_ble("CAMERA-EVENT-TAG", session) == asset
    assert resolve_from_camera(
        CameraDetection(
            asset_identifier="CAMERA-EVENT-TAG",
            confidence=0.9,
            serial_number="TEST-SERIAL",
            qr_code="TEST-QR",
        ),
        session,
    ) == asset
    assert resolve_asset("missing", "tag", session) is None


def test_camera_event_is_stored_once_and_updates_last_seen(
    camera_event_client: tuple[TestClient, Session, Camera, Asset, Zone],
) -> None:
    client, session, camera, asset, zone = camera_event_client
    timestamp = datetime.now(UTC).isoformat()
    payload = {
        "camera_id": str(camera.id),
        "event_id": "camera-event-test-1",
        "timestamp": timestamp,
        "detections": [
            {
                "asset_identifier": "CAMERA-EVENT-TAG",
                "confidence": 0.8,
                "zone_id": str(zone.id),
            },
            {
                "asset_identifier": "unknown-pump",
                "confidence": 0.4,
            },
        ],
    }

    response = client.post("/api/v1/events/camera", json=payload)

    assert response.status_code == 201
    assert response.json() == {
        "status": "accepted",
        "event_id": "camera-event-test-1",
        "detections_count": 2,
    }
    event = session.scalar(
        select(CameraEvent).where(CameraEvent.event_id == "camera-event-test-1")
    )
    assert event is not None
    assert event.asset_id is None
    assert event.confidence is None
    assert event.unknown_asset is True
    assert event.raw_payload["detections"][0]["asset_id"] == str(asset.id)
    assert event.raw_payload["detections"][0]["unknown_asset"] is False
    assert event.raw_payload["detections"][1]["asset_id"] is None
    assert event.raw_payload["detections"][1]["unknown_asset"] is True

    duplicate = client.post("/api/v1/events/camera", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json() == {"status": "duplicate", "event_id": "camera-event-test-1"}
    assert session.scalar(select(func.count()).select_from(CameraEvent)) == 1

    session.refresh(camera)
    assert camera.last_seen_at == datetime.fromisoformat(timestamp)


def test_malformed_camera_event_returns_422(
    camera_event_client: tuple[TestClient, Session, Camera, Asset, Zone],
) -> None:
    client, _, _, _, _ = camera_event_client
    response = client.post("/api/v1/events/camera", json={"event_id": "missing-fields"})
    assert response.status_code == 422


def test_camera_event_can_trigger_fusion(
    camera_event_client: tuple[TestClient, Session, Camera, Asset, Zone],
    monkeypatch,
) -> None:
    from app.routers import events

    client, _, camera, asset, zone = camera_event_client
    calls: list[str] = []

    def fake_run_fusion(asset_id: str, _db: Session) -> dict[str, str]:
        calls.append(asset_id)
        return {
            "decision_status": "confirmed",
            "confidence_band": "high",
            "zone_id": str(zone.id),
        }

    monkeypatch.setattr(events, "run_fusion", fake_run_fusion)
    response = client.post(
        "/api/v1/events/camera?trigger_fusion=true",
        json={
            "camera_id": str(camera.id),
            "event_id": "camera-event-trigger-fusion",
            "timestamp": datetime.now(UTC).isoformat(),
            "detections": [
                {
                    "asset_identifier": "CAMERA-EVENT-TAG",
                    "confidence": 0.8,
                    "zone_id": str(zone.id),
                },
                {
                    "asset_identifier": "CAMERA-EVENT-TAG",
                    "confidence": 0.7,
                    "zone_id": str(zone.id),
                },
            ],
        },
    )

    assert response.status_code == 201
    assert calls == [str(asset.id)]
    result = response.json()["fusion_results"][0]
    assert result["asset_id"] == str(asset.id)
    assert result["decision_status"] == "confirmed"
    assert result["confidence_band"] == "high"
    assert result["zone_id"] == str(zone.id)
    assert "gateway_count" in result
    assert "rssi_spread" in result
    assert "calibration" in result
