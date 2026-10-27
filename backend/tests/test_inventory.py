from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import Alert, Asset, AssetType, Facility, Floor, ParLevel, Zone


@pytest.fixture
def inventory_client() -> Iterator[tuple[TestClient, Session]]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    facility = Facility(name="Inventory test facility")
    session.add(facility)
    session.flush()
    floor = Floor(facility_id=facility.id, name="Test floor", floor_number=1)
    asset_type = AssetType(name="Inventory Pump")
    session.add_all([floor, asset_type])
    session.flush()
    ward = Zone(
        floor_id=floor.id,
        name="Inventory Ward A",
        zone_type="ward",
        polygon_json=[[0, 0], [10, 0], [10, 10], [0, 10]],
    )
    storage = Zone(
        floor_id=floor.id,
        name="Inventory Storage",
        zone_type="storage",
        polygon_json=[[10, 10], [20, 10], [20, 20], [10, 20]],
    )
    session.add_all([ward, storage])
    session.flush()
    session.add_all(
        [
            ParLevel(zone_id=ward.id, asset_type_id=asset_type.id, par_count=2),
            ParLevel(zone_id=storage.id, asset_type_id=asset_type.id, par_count=1),
            Asset(
                code="INV-AVAILABLE",
                asset_type_id=asset_type.id,
                floor_id=floor.id,
                current_zone_id=ward.id,
                operational_status="available",
                status_source="user",
                status_actor="fixture",
                status_reason="test setup",
                status_stale_after=datetime.now(UTC) + timedelta(hours=1),
            ),
            Asset(
                code="INV-SECOND-AVAILABLE",
                asset_type_id=asset_type.id,
                floor_id=floor.id,
                current_zone_id=ward.id,
                operational_status="available",
                status_source="user",
                status_actor="fixture",
                status_reason="test setup",
                status_stale_after=datetime.now(UTC) + timedelta(hours=1),
            ),
            Asset(
                code="INV-EXPIRED",
                asset_type_id=asset_type.id,
                floor_id=floor.id,
                current_zone_id=ward.id,
                operational_status="available",
                status_source="user",
                status_actor="fixture",
                status_reason="test setup",
                status_stale_after=datetime.now(UTC) - timedelta(hours=1),
            ),
            Asset(
                code="INV-UNKNOWN",
                asset_type_id=asset_type.id,
                floor_id=floor.id,
                current_zone_id=storage.id,
                operational_status="status_unknown",
                status_source="workflow_adapter",
                status_actor="fixture",
                status_reason="test setup",
            ),
        ]
    )
    session.flush()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, session
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.close()
        session.close()
        transaction.rollback()
        connection.close()


def test_inventory_counts_only_available_with_valid_confirmation(
    inventory_client: tuple[TestClient, Session],
) -> None:
    client, _ = inventory_client

    response = client.get("/api/v1/inventory")

    assert response.status_code == 200
    rows = {
        (row["zone_name"], row["asset_type_name"]): row
        for row in response.json()
    }
    storage = rows[("Inventory Storage", "Inventory Pump")]
    assert storage["usable_count"] == 0
    assert storage["status_unknown_count"] == 1
    assert storage["par_count"] == 1
    assert storage["status"] == "deficit"
    assert storage["deficit_count"] == 1
    ward = rows[("Inventory Ward A", "Inventory Pump")]
    assert ward["usable_count"] == 2
    assert ward["available_count"] == 2
    assert ward["in_use_count"] == 0
    assert ward["maintenance_count"] == 0
    assert ward["par_count"] == 2
    assert ward["status"] == "ok"
    assert ward["deficit_count"] == 0


def test_inventory_creates_one_open_alert_per_deficit_pair(
    inventory_client: tuple[TestClient, Session],
) -> None:
    client, _ = inventory_client

    assert client.get("/api/v1/inventory").status_code == 200
    assert client.post("/api/v1/alerts/reconcile").status_code == 200
    response = client.get("/api/v1/alerts", params={"status": "open"})
    assert client.get("/api/v1/alerts", params={"status": "open"}).status_code == 200

    assert response.status_code == 200
    storage_alerts = [
        alert
        for alert in response.json()
        if alert["zone_name"] == "Inventory Storage"
        and alert["asset_type_name"] == "Inventory Pump"
    ]
    assert len(storage_alerts) == 1
    assert storage_alerts[0]["title"] == "PAR deficit"
    assert storage_alerts[0]["message"] == (
        "Usable count (0) is below PAR (1). 1 additional units recommended."
    )


def test_acknowledged_alert_is_not_immediately_recreated(
    inventory_client: tuple[TestClient, Session],
) -> None:
    client, _ = inventory_client
    client.get("/api/v1/inventory")
    client.post("/api/v1/alerts/reconcile")
    open_alerts = client.get("/api/v1/alerts", params={"status": "open"}).json()
    alert = next(
        item
        for item in open_alerts
        if item["zone_name"] == "Inventory Storage"
        and item["asset_type_name"] == "Inventory Pump"
    )

    response = client.post(
        f"/api/v1/alerts/{alert['id']}/acknowledge",
        json={"actor": "demo_admin"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    assert response.json()["acknowledged_by"] == "demo_admin"

    remaining = client.get("/api/v1/alerts", params={"status": "open"}).json()
    assert all(item["id"] != alert["id"] for item in remaining)
    acknowledged = client.get(
        "/api/v1/alerts", params={"status": "acknowledged"}
    ).json()
    assert any(item["id"] == alert["id"] for item in acknowledged)


def test_dismissed_alert_stays_dismissed_until_deficit_resolves(
    inventory_client: tuple[TestClient, Session],
) -> None:
    client, _ = inventory_client
    client.post("/api/v1/alerts/reconcile")
    open_alerts = client.get("/api/v1/alerts", params={"status": "open"}).json()
    alert = next(
        item
        for item in open_alerts
        if item["zone_name"] == "Inventory Storage"
        and item["asset_type_name"] == "Inventory Pump"
    )

    response = client.post(f"/api/v1/alerts/{alert['id']}/dismiss")

    assert response.status_code == 200
    assert response.json() == {"id": alert["id"], "status": "dismissed"}
    remaining = client.get("/api/v1/alerts", params={"status": "open"}).json()
    assert all(item["id"] != alert["id"] for item in remaining)


def test_prohibited_alert_text_is_rejected_at_write_time(
    inventory_client: tuple[TestClient, Session],
) -> None:
    client, session = inventory_client
    zone = session.query(Zone).filter_by(name="Inventory Ward A").one()
    asset_type = session.query(AssetType).filter_by(name="Inventory Pump").one()
    base_payload = {
        "alert_type": "operational_notice",
        "zone_id": str(zone.id),
        "asset_type_id": str(asset_type.id),
        "count": 0,
        "par_count": 1,
        "severity": "medium",
        "message": "Please review this inventory record.",
    }
    prohibited = client.post(
        "/api/v1/alerts",
        json={**base_payload, "title": "Possible theft"},
    )
    named = client.post(
        "/api/v1/alerts",
        json={**base_payload, "title": "Alex Smith review"},
    )
    assert prohibited.status_code == 422
    assert named.status_code == 422


def test_simulator_topology_returns_asset_and_zone_ids(
    inventory_client: tuple[TestClient, Session],
) -> None:
    client, _ = inventory_client

    response = client.get("/api/v1/simulator/topology")

    assert response.status_code == 200
    topology = response.json()
    assert any(asset["code"] == "INV-AVAILABLE" for asset in topology["assets"])
    assert any(zone["name"] == "Inventory Ward A" for zone in topology["zones"])
    assert "cameras" in topology
    assert "gateways" in topology
