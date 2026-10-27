from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import Asset, AssetType, Camera, Facility, Floor, Zone


@pytest.fixture
def fusion_trigger_client() -> Iterator[tuple[TestClient, Session, Camera, Asset, Zone]]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    facility = Facility(name="Fusion trigger test facility")
    session.add(facility)
    session.flush()
    floor = Floor(facility_id=facility.id, name="Test floor", floor_number=1)
    asset_type = AssetType(name="Test pump")
    session.add_all([floor, asset_type])
    session.flush()
    zone = Zone(
        floor_id=floor.id,
        name="Fusion trigger zone",
        zone_type="ward",
        polygon_json=[[0, 0], [10, 0], [10, 10], [0, 10]],
    )
    session.add(zone)
    session.flush()
    asset = Asset(
        code="P-001",
        serial_number="FUSION-TRIGGER-SERIAL",
        qr_code="FUSION-TRIGGER-QR",
        asset_type_id=asset_type.id,
        floor_id=floor.id,
        operational_status="status_unknown",
        status_source="workflow_adapter",
        status_actor="test",
        status_reason="test setup",
    )
    camera = Camera(
        floor_id=floor.id,
        name="Fusion trigger camera",
        coverage_zone_ids=[],
        heartbeat_timeout_s=60,
        status="online",
    )
    session.add_all([asset, camera])
    session.flush()

    def override_get_db() -> Iterator[Session]:
        yield session

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


def test_camera_event_fusion_updates_asset_detail(
    fusion_trigger_client: tuple[TestClient, Session, Camera, Asset, Zone],
) -> None:
    client, session, camera, asset, zone = fusion_trigger_client
    response = client.post(
        "/api/v1/events/camera?trigger_fusion=true",
        json={
            "camera_id": str(camera.id),
            "event_id": "fusion-trigger-e2e",
            "timestamp": datetime.now(UTC).isoformat(),
            "detections": [
                {
                    "asset_identifier": asset.serial_number,
                    "confidence": 0.9,
                    "zone_id": str(zone.id),
                }
            ],
        },
    )

    assert response.status_code == 201
    session.refresh(asset)
    assert asset.current_zone_id == zone.id

    detail_response = client.get(f"/api/v1/assets/{asset.id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["current_zone_id"] == str(zone.id)
    assert detail["confidence_band"] is not None
