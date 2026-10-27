from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import (
    AssetCurrentState,
    Camera,
    CameraEvent,
    Facility,
    Floor,
    Gateway,
    LocationEstimate,
)


@pytest.fixture
def sensor_client() -> Iterator[tuple[TestClient, Session, Camera, Gateway]]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    facility = Facility(name="Heartbeat test facility")
    session.add(facility)
    session.flush()
    floor = Floor(facility_id=facility.id, name="Test floor", floor_number=1)
    session.add(floor)
    session.flush()

    camera = Camera(
        floor_id=floor.id,
        name="Heartbeat test camera",
        coverage_zone_ids=[],
        heartbeat_timeout_s=60,
        status="offline",
    )
    gateway = Gateway(
        floor_id=floor.id,
        name="Heartbeat test gateway",
        x=0,
        y=0,
        heartbeat_timeout_s=60,
        status="offline",
    )
    session.add_all([camera, gateway])
    session.flush()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, session, camera, gateway
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.close()
        session.close()
        transaction.rollback()
        connection.close()


@pytest.mark.parametrize(
    ("age_seconds", "expected_status"),
    [(5, "active"), (90, "degraded"), (130, "offline")],
)
def test_camera_heartbeat_updates_status_without_creating_events(
    sensor_client: tuple[TestClient, Session, Camera, Gateway],
    age_seconds: int,
    expected_status: str,
) -> None:
    client, session, camera, _ = sensor_client
    timestamp = datetime.now(UTC) - timedelta(seconds=age_seconds)

    response = client.post(
        f"/api/v1/sensors/{camera.id}/heartbeat",
        json={"timestamp": timestamp.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    session.refresh(camera)
    assert camera.status == expected_status
    assert camera.last_heartbeat_at == timestamp
    assert session.scalar(select(func.count()).select_from(CameraEvent)) == 0
    assert session.scalar(select(func.count()).select_from(LocationEstimate)) == 0
    assert session.scalar(select(func.count()).select_from(AssetCurrentState)) == 0


def test_gateway_heartbeat_is_supported(
    sensor_client: tuple[TestClient, Session, Camera, Gateway],
) -> None:
    client, session, _, gateway = sensor_client
    timestamp = datetime.now(UTC).isoformat()

    response = client.post(
        f"/api/v1/sensors/{gateway.id}/heartbeat",
        json={"timestamp": timestamp},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    session.refresh(gateway)
    assert gateway.status == "active"
    assert gateway.last_heartbeat_at is not None


def test_missing_sensor_returns_404(
    sensor_client: tuple[TestClient, Session, Camera, Gateway],
) -> None:
    client, _, _, _ = sensor_client
    response = client.post(
        "/api/v1/sensors/00000000-0000-0000-0000-000000000000/heartbeat",
        json={"timestamp": datetime.now(UTC).isoformat()},
    )
    assert response.status_code == 404


def test_malformed_heartbeat_returns_422(
    sensor_client: tuple[TestClient, Session, Camera, Gateway],
) -> None:
    client, _, camera, _ = sensor_client
    response = client.post(
        f"/api/v1/sensors/{camera.id}/heartbeat",
        json={"timestamp": "not-a-datetime"},
    )
    assert response.status_code == 422
