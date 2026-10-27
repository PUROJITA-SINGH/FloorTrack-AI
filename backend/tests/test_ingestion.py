from collections.abc import Iterator
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import (
    Asset,
    AssetCurrentState,
    AssetType,
    BleEvent,
    Camera,
    CameraEvent,
    CoverageFigure,
    Facility,
    Floor,
    Gateway,
    FusionDecision,
    LocationEstimate,
    Tag,
    Zone,
)

class IngestionContext(TypedDict):
    client: TestClient
    session: Session
    asset: Asset
    camera: Camera
    gateway: Gateway
    gateways: list[Gateway]
    tag: Tag


@pytest.fixture
def ingestion_context(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[IngestionContext]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    facility = Facility(name="Ingestion test facility")
    session.add(facility)
    session.flush()
    floor = Floor(facility_id=facility.id, name="Test floor", floor_number=1)
    asset_type = AssetType(name="Test infusion pump")
    session.add_all([floor, asset_type])
    session.flush()

    asset = Asset(
        code="INGESTION-TEST",
        serial_number="INGESTION-SERIAL",
        qr_code="INGESTION-QR",
        asset_type_id=asset_type.id,
        floor_id=floor.id,
        operational_status="status_unknown",
        status_source="workflow_adapter",
        status_actor="test",
        status_reason="test setup",
    )
    camera = Camera(
        floor_id=floor.id,
        name="Ingestion test camera",
        coverage_zone_ids=[],
        heartbeat_timeout_s=60,
        status="offline",
    )
    gateway = Gateway(
        floor_id=floor.id,
        name="Ingestion test gateway",
        x=10,
        y=10,
        heartbeat_timeout_s=60,
        status="offline",
    )
    other_gateways = [
        Gateway(
            floor_id=floor.id,
            name=f"Ingestion test gateway {index}",
            x=index * 10,
            y=index * 10,
            heartbeat_timeout_s=60,
            status="offline",
        )
        for index in (2, 3)
    ]
    session.add_all([asset, camera, gateway, *other_gateways])
    session.flush()
    tag = Tag(asset_id=asset.id, tag_type="ble", tag_value="INGESTION-TAG")
    session.add(tag)
    session.flush()

    def override_get_db() -> Iterator[Session]:
        yield session

    from app.routers import events

    monkeypatch.setattr(events, "_run_fusion_in_background", lambda _asset_id: None)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield {
            "client": client,
            "session": session,
            "asset": asset,
            "camera": camera,
            "gateway": gateway,
            "gateways": [gateway, *other_gateways],
            "tag": tag,
        }
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.close()
        session.close()
        transaction.rollback()
        connection.close()


def camera_payload(context: IngestionContext, event_id: str) -> dict[str, object]:
    camera = context["camera"]
    asset = context["asset"]
    return {
        "camera_id": str(camera.id),
        "event_id": event_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "detections": [
            {
                "asset_identifier": asset.serial_number,
                "confidence": 0.85,
            }
        ],
    }


def ble_payload(
    context: IngestionContext,
    event_id: str,
    readings: list[dict[str, object]],
) -> dict[str, object]:
    tag = context["tag"]
    return {
        "tag_id": tag.tag_value,
        "event_id": event_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "readings": readings,
    }


def test_camera_valid(ingestion_context: IngestionContext) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]

    response = client.post(
        "/api/v1/events/camera",
        json=camera_payload(ingestion_context, "ingestion-camera-valid"),
    )

    assert response.status_code == 201
    event = session.scalar(
        select(CameraEvent).where(CameraEvent.event_id == "ingestion-camera-valid")
    )
    assert event is not None
    assert event.raw_payload["detections"][0]["asset_id"] == str(ingestion_context["asset"].id)


def test_ble_trigger_fusion(ingestion_context: IngestionContext, monkeypatch) -> None:
    from app.routers import events

    client = ingestion_context["client"]
    asset = ingestion_context["asset"]
    calls: list[str] = []

    def fake_run_fusion(asset_id: str, _db: Session) -> dict[str, str]:
        calls.append(asset_id)
        return {
            "decision_status": "confirmed",
            "confidence_band": "high",
            "zone_id": "zone-1",
        }

    monkeypatch.setattr(events, "run_fusion", fake_run_fusion)
    response = client.post(
        "/api/v1/events/ble?trigger_fusion=true",
        json=ble_payload(
            ingestion_context,
            "ingestion-ble-trigger-fusion",
            [{"gateway_id": str(ingestion_context["gateway"].id), "rssi": -52}],
        ),
    )

    assert response.status_code == 201
    assert calls == [str(asset.id)]
    assert response.json()["fusion_results"] == [
        {
            "asset_id": str(asset.id),
            "decision_status": "confirmed",
            "confidence_band": "high",
            "zone_id": "zone-1",
            "reason": None,
            "review_state": None,
            "review_alert_id": None,
            "camera_zone_id": None,
            "ble_zone_id": None,
            "evidence_links": [],
            "gateway_count": None,
            "rssi_spread": None,
            "calibration": None,
        }
    ]


def test_combined_ingest_fuses_resolved_asset_once(
    ingestion_context: IngestionContext,
    monkeypatch,
) -> None:
    from app.routers import events

    client = ingestion_context["client"]
    asset = ingestion_context["asset"]
    calls: list[str] = []

    def fake_run_fusion(asset_id: str, _db: Session) -> dict[str, str]:
        calls.append(asset_id)
        return {
            "decision_status": "confirmed",
            "confidence_band": "high",
            "zone_id": "zone-1",
        }

    monkeypatch.setattr(events, "run_fusion", fake_run_fusion)
    response = client.post(
        "/api/v1/events/ingest-and-fuse",
        json={
            "camera_events": [
                camera_payload(ingestion_context, "combined-camera-trigger-fusion")
            ],
            "ble_events": [
                ble_payload(
                    ingestion_context,
                    "combined-ble-trigger-fusion",
                    [{"gateway_id": str(ingestion_context["gateway"].id), "rssi": -52}],
                )
            ],
        },
    )

    assert response.status_code == 200
    assert calls == [str(asset.id)]
    assert response.json() == {
        "camera_accepted": 1,
        "ble_accepted": 1,
        "fusion_results": [
            {
                "asset_id": str(asset.id),
                "decision_status": "confirmed",
                "confidence_band": "high",
                "zone_id": "zone-1",
                "reason": None,
                "review_state": None,
                "review_alert_id": None,
                "camera_zone_id": None,
                "ble_zone_id": None,
                "evidence_links": [],
                "gateway_count": None,
                "rssi_spread": None,
                "calibration": None,
            }
        ],
    }


def test_camera_and_ble_fusion_is_visible_in_asset_detail(
    ingestion_context: IngestionContext,
) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    asset = ingestion_context["asset"]
    camera = ingestion_context["camera"]
    zone = Zone(
        floor_id=asset.floor_id,
        name="Fusion output zone",
        zone_type="ward",
        polygon_json=[[0, 0], [30, 0], [30, 30], [0, 30]],
    )
    session.add(zone)
    session.flush()

    ble_response = client.post(
        "/api/v1/events/ble?trigger_fusion=true",
        json=ble_payload(
            ingestion_context,
            "fusion-pipeline-ble",
            [{"gateway_id": str(ingestion_context["gateway"].id), "rssi": -48}],
        ),
    )
    assert ble_response.status_code == 201

    camera_payload_data = camera_payload(
        ingestion_context,
        "fusion-pipeline-camera",
    )
    camera_payload_data["detections"] = [
        {
            "asset_identifier": asset.serial_number,
            "confidence": 0.85,
            "zone_id": str(zone.id),
        }
    ]
    camera_response = client.post(
        "/api/v1/events/camera?trigger_fusion=true",
        json=camera_payload_data,
    )
    assert camera_response.status_code == 201

    detail_response = client.get(f"/api/v1/assets/{asset.id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()

    assert detail["current_zone_id"] == str(zone.id)
    assert detail["zone"] == zone.name
    assert detail["confidence_band"] == "low"
    assert detail["decision_status"] == "confirmed"
    assert detail["last_fusion_at"] is not None
    assert detail["fusion_detail"]["camera_zone"] == zone.name
    assert detail["fusion_detail"]["ble_zone"] is None
    assert detail["fusion_detail"]["gateway_count"] == 1
    assert isinstance(detail["fusion_detail"]["confidence_breakdown"], dict)
    assert detail["fusion_detail"]["reason"]

    current_state = session.scalar(
        select(AssetCurrentState).where(AssetCurrentState.asset_id == asset.id)
    )
    assert current_state is not None
    assert current_state.zone_id == zone.id
    decision = session.get(FusionDecision, current_state.last_fusion_decision_id)
    assert decision is not None
    assert decision.confidence_breakdown == detail["fusion_detail"]["confidence_breakdown"]
    assert detail["disagreement_reason"] is None
    assert camera.last_seen_at is not None


def test_conflicting_camera_and_ble_expose_disagreement_reason(
    ingestion_context: IngestionContext,
) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    asset = ingestion_context["asset"]
    camera = ingestion_context["camera"]
    camera_zone = Zone(
        floor_id=asset.floor_id,
        name="Ward A",
        zone_type="ward",
        polygon_json=[[0, 0], [30, 0], [30, 30], [0, 30]],
    )
    ble_zone = Zone(
        floor_id=asset.floor_id,
        name="Ward B",
        zone_type="ward",
        polygon_json=[[70, 70], [100, 70], [100, 100], [70, 100]],
    )
    ble_gateway = Gateway(
        floor_id=asset.floor_id,
        name="Conflict gateway",
        x=90,
        y=90,
        heartbeat_timeout_s=60,
        status="online",
    )
    ble_gateway_2 = Gateway(
        floor_id=asset.floor_id,
        name="Conflict gateway 2",
        x=95,
        y=95,
        heartbeat_timeout_s=60,
        status="online",
    )
    session.add_all([camera_zone, ble_zone, ble_gateway, ble_gateway_2])
    session.flush()

    ble_response = client.post(
        "/api/v1/events/ble?trigger_fusion=true",
        json=ble_payload(
            ingestion_context,
            "conflict-pipeline-ble",
            [
                {"gateway_id": str(ble_gateway.id), "rssi": -48},
                {"gateway_id": str(ble_gateway_2.id), "rssi": -52},
            ],
        ),
    )
    assert ble_response.status_code == 201

    camera_response = client.post(
        "/api/v1/events/camera?trigger_fusion=true",
        json={
            "camera_id": str(camera.id),
            "event_id": "conflict-pipeline-camera",
            "timestamp": datetime.now(UTC).isoformat(),
            "detections": [
                {
                    "asset_identifier": asset.serial_number,
                    "confidence": 0.9,
                    "zone_id": str(camera_zone.id),
                }
            ],
        },
    )
    assert camera_response.status_code == 201
    fusion_results = camera_response.json()["fusion_results"]
    assert fusion_results[0]["decision_status"] == "sensor_disagreement"

    detail_response = client.get(f"/api/v1/assets/{asset.id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()

    assert detail["decision_status"] == "sensor_disagreement"
    assert detail["disagreement_reason"] is not None
    assert "Sensor disagreement" in detail["disagreement_reason"]
    assert "camera reports Ward A" in detail["disagreement_reason"]
    assert "BLE reports Ward B" in detail["disagreement_reason"]
    assert detail["fusion_detail"]["camera_zone"] == "Ward A"
    assert detail["fusion_detail"]["ble_zone"] == "Ward B"
    assert detail["fusion_detail"]["reason"] == detail["disagreement_reason"]


def test_ble_only_ingestion_returns_camera_coverage_without_state_changes(
    ingestion_context: IngestionContext,
) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    asset = ingestion_context["asset"]
    camera = ingestion_context["camera"]
    gateway = ingestion_context["gateway"]
    zone = Zone(
        floor_id=asset.floor_id,
        name="Covered zone",
        zone_type="ward",
        polygon_json=[[0, 0], [30, 0], [30, 30], [0, 30]],
    )
    session.add(zone)
    session.flush()
    camera.coverage_zone_ids = [str(zone.id)]
    camera.last_seen_at = datetime.now(UTC)
    original_status = asset.operational_status
    state = AssetCurrentState(
        asset_id=asset.id,
        zone_id=zone.id,
        confidence_band="medium",
        decision_status="confirmed",
    )
    asset.current_zone_id = zone.id
    session.add(state)
    session.flush()
    original_updated_at = state.updated_at

    ingest_response = client.post(
        "/api/v1/events/ble?trigger_fusion=true",
        json=ble_payload(
            ingestion_context,
            "ble-only-camera-silent-ingestion",
            [
                {"gateway_id": str(gateway.id), "rssi": -48},
            ],
        ),
    )
    assert ingest_response.status_code == 201
    fusion_result = ingest_response.json()["fusion_results"][0]
    assert fusion_result["asset_id"] == str(asset.id)
    assert fusion_result["status"] == "camera_silent"
    assert fusion_result["state_changed"] is False
    assert fusion_result["coverage"] == 100.0
    assert fusion_result["camera_last_seen"] == camera.last_seen_at.isoformat()

    session.refresh(state)
    session.refresh(asset)
    detail_response = client.get(f"/api/v1/assets/{asset.id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()

    assert state.zone_id == zone.id
    assert state.confidence_band == "medium"
    assert state.decision_status == "confirmed"
    assert state.updated_at == original_updated_at
    assert asset.operational_status == original_status
    assert asset.last_fusion_at is None
    assert detail["current_zone_id"] == str(zone.id)
    assert detail["confidence_band"] == "medium"
    assert detail["operational_status"] == original_status
    assert detail["camera_coverage"] == 100.0
    assert datetime.fromisoformat(
        detail["camera_last_seen"].replace("Z", "+00:00")
    ) == camera.last_seen_at
    coverage_figure = session.scalar(
        select(CoverageFigure).where(CoverageFigure.zone_id == zone.id)
    )
    assert coverage_figure is not None
    assert coverage_figure.coverage_percent == 100.0


def test_camera_malformed(ingestion_context: IngestionContext) -> None:
    client = ingestion_context["client"]

    response = client.post("/api/v1/events/camera", json={"event_id": "missing-fields"})

    assert response.status_code == 422
    assert "detail" in response.json()


def test_camera_duplicate(ingestion_context: IngestionContext) -> None:
    client = ingestion_context["client"]
    payload = camera_payload(ingestion_context, "ingestion-camera-duplicate")

    first_response = client.post("/api/v1/events/camera", json=payload)
    second_response = client.post("/api/v1/events/camera", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 200
    assert second_response.json() == {
        "status": "duplicate",
        "event_id": "ingestion-camera-duplicate",
    }


def test_camera_last_seen_does_not_move_backwards(
    ingestion_context: IngestionContext,
) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    camera = ingestion_context["camera"]
    newer = datetime.now(UTC)
    older = newer.replace(year=newer.year - 1)
    first_payload = camera_payload(ingestion_context, "camera-newer-timestamp")
    first_payload["timestamp"] = newer.isoformat()
    second_payload = camera_payload(ingestion_context, "camera-older-timestamp")
    second_payload["timestamp"] = older.isoformat()

    assert client.post("/api/v1/events/camera", json=first_payload).status_code == 201
    assert client.post("/api/v1/events/camera", json=second_payload).status_code == 201

    session.refresh(camera)
    assert camera.last_seen_at == newer


def test_ble_single_gateway(ingestion_context: IngestionContext) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    asset = ingestion_context["asset"]
    readings = [{"gateway_id": str(ingestion_context["gateway"].id), "rssi": -48}]

    response = client.post(
        "/api/v1/events/ble",
        json=ble_payload(ingestion_context, "ingestion-ble-single", readings),
    )

    assert response.status_code == 201
    event = session.scalar(
        select(BleEvent).where(BleEvent.event_id == "ingestion-ble-single")
    )
    assert event is not None
    assert event.readings == readings
    assert session.scalar(
        select(func.count()).select_from(LocationEstimate).where(
            LocationEstimate.asset_id == asset.id
        )
    ) == 0


def test_ble_malformed_reading_is_rejected_before_persistence(
    ingestion_context: IngestionContext,
) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]

    response = client.post(
        "/api/v1/events/ble",
        json=ble_payload(
            ingestion_context,
            "ingestion-ble-malformed",
            [{"gateway_id": "gateway-1", "rssi": "not-a-number"}],
        ),
    )

    assert response.status_code == 422
    assert session.scalar(
        select(func.count()).select_from(BleEvent).where(
            BleEvent.event_id == "ingestion-ble-malformed"
        )
    ) == 0


def test_ble_concurrent_duplicate_returns_duplicate_after_rollback(
    ingestion_context: IngestionContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import events

    duplicate_id = UUID("00000000-0000-0000-0000-000000000001")

    class ConcurrentDuplicateSession:
        def __init__(self) -> None:
            self.scalar_calls = 0
            self.rolled_back = False

        def scalar(self, statement):
            del statement
            self.scalar_calls += 1
            return duplicate_id if self.scalar_calls == 3 else None

        def add(self, instance) -> None:
            del instance

        def scalars(self, statement):
            del statement
            return type("Result", (), {"all": lambda self: []})()

        def get(self, model, _key):
            return model(capabilities=[])

        def commit(self) -> None:
            raise IntegrityError("insert", {}, RuntimeError("duplicate event_id"))

        def rollback(self) -> None:
            self.rolled_back = True

    session = ConcurrentDuplicateSession()
    def resolve_unknown_tag(tag_id: str, db: ConcurrentDuplicateSession) -> None:
        assert tag_id == "unknown-tag"
        assert db is session
        return None

    monkeypatch.setattr(events, "resolve_from_ble", resolve_unknown_tag)
    payload = events.BleEventPayload(
        tag_id="unknown-tag",
        event_id="ble-race",
        timestamp=datetime.now(UTC),
        readings=[
            {
                "gateway_id": str(ingestion_context["gateway"].id),
                "rssi": -50,
            }
        ],
    )

    response = events.ingest_ble_event(payload, db=session)

    assert response.status_code == 200
    assert response.body == b'{"status":"duplicate","event_id":"ble-race"}'
    assert session.rolled_back


def test_ble_empty_readings_are_rejected_as_silence(
    ingestion_context: IngestionContext,
) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    response = client.post(
        "/api/v1/events/ble",
        json=ble_payload(ingestion_context, "ingestion-ble-empty", []),
    )

    assert response.status_code == 422
    assert session.scalar(
        select(BleEvent).where(BleEvent.event_id == "ingestion-ble-empty")
    ) is None


def test_ble_multi_gateway(ingestion_context: IngestionContext) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    gateways = ingestion_context["gateways"]
    readings = [
        {"gateway_id": str(gateway.id), "rssi": -45 - index}
        for index, gateway in enumerate(gateways)
    ]

    response = client.post(
        "/api/v1/events/ble",
        json=ble_payload(ingestion_context, "ingestion-ble-multi", readings),
    )

    assert response.status_code == 201
    event = session.scalar(
        select(BleEvent).where(BleEvent.event_id == "ingestion-ble-multi")
    )
    assert event is not None
    assert event.readings == readings


def test_heartbeat(ingestion_context: IngestionContext) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    camera = ingestion_context["camera"]
    timestamp = datetime.now(UTC).isoformat()

    response = client.post(
        f"/api/v1/sensors/{camera.id}/heartbeat",
        json={"timestamp": timestamp},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    session.refresh(camera)
    assert camera.last_heartbeat_at == datetime.fromisoformat(timestamp)
    for model in (CameraEvent, BleEvent, LocationEstimate, AssetCurrentState):
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_heartbeat_unknown_sensor(ingestion_context: IngestionContext) -> None:
    client = ingestion_context["client"]

    response = client.post(
        "/api/v1/sensors/00000000-0000-0000-0000-000000000000/heartbeat",
        json={"timestamp": datetime.now(UTC).isoformat()},
    )

    assert response.status_code == 404


def test_unknown_identifier(ingestion_context: IngestionContext) -> None:
    client = ingestion_context["client"]
    session = ingestion_context["session"]
    payload = camera_payload(ingestion_context, "ingestion-camera-unknown")
    payload["detections"] = [
        {
            "asset_identifier": "not-a-known-asset",
            "confidence": 0.2,
        }
    ]

    response = client.post("/api/v1/events/camera", json=payload)

    assert response.status_code == 201
    event = session.scalar(
        select(CameraEvent).where(CameraEvent.event_id == "ingestion-camera-unknown")
    )
    assert event is not None
    assert event.unknown_asset is True
    assert event.raw_payload["detections"][0]["asset_id"] is None
    assert event.raw_payload["detections"][0]["unknown_asset"] is True
