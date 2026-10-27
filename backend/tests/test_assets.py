from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import CONFIRMATION_WINDOW
from app.database import engine, get_db
from app.main import app
from app.models import (
    Asset,
    AssetCurrentState,
    AssetStatusHistory,
    AssetType,
    Facility,
    Floor,
    Zone,
)


@pytest.fixture
def assets_client() -> Iterator[tuple[TestClient, Session, Asset, AssetType, Zone]]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    facility = Facility(name="Asset API test facility")
    session.add(facility)
    session.flush()
    floor = Floor(facility_id=facility.id, name="Test floor", floor_number=1)
    asset_type = AssetType(name="Infusion Pump")
    session.add_all([floor, asset_type])
    session.flush()
    zone = Zone(
        floor_id=floor.id,
        name="Ward A",
        zone_type="ward",
        polygon_json=[[0, 0], [10, 0], [10, 10], [0, 10]],
    )
    session.add(zone)
    session.flush()
    asset = Asset(
        code="ASSET-API-1",
        serial_number="ASSET-SERIAL-1",
        qr_code="ASSET-QR-1",
        asset_type_id=asset_type.id,
        floor_id=floor.id,
        current_zone_id=zone.id,
        operational_status="status_unknown",
        status_source="workflow_adapter",
        status_actor="fixture",
        status_reason="test setup",
    )
    session.add(asset)
    session.flush()
    session.add(
        AssetCurrentState(
            asset_id=asset.id,
            zone_id=zone.id,
            confidence_band="medium",
            decision_status="confirmed",
        )
    )
    session.flush()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, session, asset, asset_type, zone
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.close()
        session.close()
        transaction.rollback()
        connection.close()


def test_user_status_update_records_history_in_one_transaction(
    assets_client: tuple[TestClient, Session, Asset, AssetType, Zone],
) -> None:
    client, session, asset, _, _ = assets_client
    response = client.post(
        f"/api/v1/assets/{asset.id}/operational-status",
        json={
            "status": "available",
            "source": "user",
            "actor": "admin",
            "reason": "confirmed for demo",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["source"] == "user"
    confirmed_at = datetime.fromisoformat(body["confirmed_at"])
    stale_after = datetime.fromisoformat(body["stale_after"])
    assert stale_after - confirmed_at == CONFIRMATION_WINDOW

    session.refresh(asset)
    assert asset.operational_status == "available"
    assert asset.status_actor == "admin"
    assert asset.status_reason == "confirmed for demo"
    assert session.scalar(
        select(func.count()).select_from(AssetStatusHistory).where(
            AssetStatusHistory.asset_id == asset.id
        )
    ) == 1


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"status": "available", "source": "sensor", "actor": "x", "reason": "x"}, "Invalid source"),
        ({"status": "available", "source": "user", "reason": "x"}, "actor is required"),
        ({"status": "available", "source": "user", "actor": "x"}, "reason is required"),
        (
            {"status": "available", "source": "workflow_adapter", "reason": "x"},
            "adapter_name is required",
        ),
    ],
)
def test_invalid_status_update_returns_400(
    assets_client: tuple[TestClient, Session, Asset, AssetType, Zone],
    payload: dict[str, str],
    detail: str,
) -> None:
    client, _, asset, _, _ = assets_client
    response = client.post(
        f"/api/v1/assets/{asset.id}/operational-status",
        json=payload,
    )
    assert response.status_code == 400
    assert detail in response.json()["detail"]


def test_unsupported_operational_status_is_rejected(
    assets_client: tuple[TestClient, Session, Asset, AssetType, Zone],
) -> None:
    client, _, asset, _, _ = assets_client

    response = client.post(
        f"/api/v1/assets/{asset.id}/operational-status",
        json={
            "status": "broken",
            "source": "user",
            "actor": "admin",
            "reason": "invalid status test",
        },
    )

    assert response.status_code == 422


def test_workflow_adapter_uses_adapter_name_as_actor(
    assets_client: tuple[TestClient, Session, Asset, AssetType, Zone],
) -> None:
    client, session, asset, _, _ = assets_client
    response = client.post(
        f"/api/v1/assets/{asset.id}/operational-status",
        json={
            "status": "maintenance",
            "source": "workflow_adapter",
            "adapter_name": "bed-management",
            "reason": "workflow update",
        },
    )
    assert response.status_code == 200
    session.refresh(asset)
    history = session.scalar(
        select(AssetStatusHistory).where(AssetStatusHistory.asset_id == asset.id)
    )
    assert history is not None
    assert history.actor == "bed-management"
    assert history.adapter_name == "bed-management"


def test_asset_not_found_returns_404(
    assets_client: tuple[TestClient, Session, Asset, AssetType, Zone],
) -> None:
    client, _, _, _, _ = assets_client
    response = client.get("/api/v1/assets/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_asset_detail_includes_zone_and_status(
    assets_client: tuple[TestClient, Session, Asset, AssetType, Zone],
) -> None:
    client, _, asset, _, _ = assets_client
    response = client.get(f"/api/v1/assets/{asset.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["zone"] == "Ward A"
    assert body["confidence_band"] == "medium"
    assert body["freshness"] is None
    assert body["operational_status"] == "status_unknown"
    assert body["disagreement_reason"] is None
    assert body["camera_coverage"] is None
    assert body["camera_last_seen"] is None


def test_asset_list_supports_search_and_asset_type_filter(
    assets_client: tuple[TestClient, Session, Asset, AssetType, Zone],
) -> None:
    client, _, asset, asset_type, _ = assets_client

    response = client.get(
        "/api/v1/assets",
        params={"search": "SERIAL-1", "asset_type": asset_type.name},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(asset.id)]
