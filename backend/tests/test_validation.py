from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import (
    Asset,
    AssetCurrentState,
    AssetType,
    AssetStatusHistory,
    Alert,
    BleEvent,
    Camera,
    CameraEvent,
    Facility,
    Floor,
    FusionDecision,
    Gateway,
    LocationEstimate,
    ParLevel,
    Tag,
    Zone,
)
from app.services.confidence import compute_confidence
from app.services.fusion import run_fusion
from app.services.status_sweep import run_status_expiry_sweep


class ValidationContext(TypedDict):
    client: TestClient
    session: Session
    asset: Asset
    asset_type: AssetType
    camera: Camera
    gateways: list[Gateway]
    tag: Tag
    zone_a: Zone
    zone_b: Zone


@pytest.fixture
def validation_context(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ValidationContext]:
    try:
        connection = engine.connect()
    except OperationalError as error:
        pytest.skip(f"PostgreSQL is unavailable: {error.orig}")
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    facility = Facility(name=f"Validation facility {uuid4()}")
    session.add(facility)
    session.flush()
    floor = Floor(facility_id=facility.id, name="Validation floor", floor_number=1)
    asset_type = AssetType(name=f"Validation pump {uuid4()}")
    session.add_all([floor, asset_type])
    session.flush()

    zone_a = Zone(
        floor_id=floor.id,
        name="Validation Ward A",
        zone_type="ward",
        polygon_json=[[0, 0], [40, 0], [40, 40], [0, 40]],
    )
    zone_b = Zone(
        floor_id=floor.id,
        name="Validation Ward B",
        zone_type="ward",
        polygon_json=[[60, 60], [100, 60], [100, 100], [60, 100]],
    )
    session.add_all([zone_a, zone_b])
    session.flush()

    asset = Asset(
        code=f"VALIDATION-{uuid4()}",
        serial_number=f"VALIDATION-SERIAL-{uuid4()}",
        qr_code=f"VALIDATION-QR-{uuid4()}",
        asset_type_id=asset_type.id,
        floor_id=floor.id,
        current_zone_id=zone_a.id,
        operational_status="available",
        status_source="user",
        status_actor="validation",
        status_reason="test fixture",
        status_stale_after=datetime.now(UTC) + timedelta(hours=2),
    )
    session.add(asset)
    session.flush()
    tag = Tag(asset_id=asset.id, tag_type="ble", tag_value=f"VALIDATION-TAG-{uuid4()}")
    camera = Camera(
        floor_id=floor.id,
        name=f"Validation camera {uuid4()}",
        coverage_zone_ids=[str(zone_a.id), str(zone_b.id)],
        heartbeat_timeout_s=10,
        status="active",
    )
    gateways = [
        Gateway(
            floor_id=floor.id,
            name=f"Validation gateway {index}",
            x=x,
            y=y,
            heartbeat_timeout_s=10,
            status="active",
        )
        for index, (x, y) in enumerate(
            ((10, 10), (30, 30), (70, 70), (90, 90)),
            start=1,
        )
    ]
    session.add_all([tag, camera, *gateways])
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
            "asset_type": asset_type,
            "camera": camera,
            "gateways": gateways,
            "tag": tag,
            "zone_a": zone_a,
            "zone_b": zone_b,
        }
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.close()
        session.close()
        transaction.rollback()
        connection.close()


def _camera_payload(
    context: ValidationContext,
    event_id: str,
    zone: Zone | None = None,
    confidence: float = 0.95,
) -> dict[str, object]:
    return {
        "camera_id": str(context["camera"].id),
        "event_id": event_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "detections": [
            {
                "asset_identifier": context["asset"].serial_number,
                "confidence": confidence,
                "zone_id": str(zone.id) if zone else None,
            }
        ],
    }


def _ble_payload(
    context: ValidationContext,
    event_id: str,
    readings: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "tag_id": context["tag"].tag_value,
        "event_id": event_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "readings": readings,
    }


def _zone_readings(
    context: ValidationContext,
    zone: Zone,
    gateway_indices: tuple[int, ...] | None = None,
) -> list[dict[str, object]]:
    gateways = context["gateways"]
    assert isinstance(gateways, list)
    if zone == context["zone_a"]:
        values = (-44, -55, -100, -105)
        selected_indices = gateway_indices or (0, 1)
    else:
        values = (-100, -105, -44, -55)
        selected_indices = gateway_indices or (2, 3)
    return [
        {
            "gateway_id": str(gateways[index].id),
            "rssi": values[index],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        for index in selected_indices
    ]


def _add_camera_event(
    context: ValidationContext,
    event_id: str,
    zone: Zone,
    confidence: float,
) -> None:
    session = context["session"]
    asset = context["asset"]
    camera = context["camera"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    assert isinstance(camera, Camera)
    session.add(
        CameraEvent(
            camera_id=camera.id,
            asset_id=asset.id,
            event_id=event_id,
            timestamp=datetime.now(UTC),
            zone_id=zone.id,
            confidence=confidence,
            raw_payload={
                "detections": [
                    {
                        "asset_id": str(asset.id),
                        "asset_identifier": asset.serial_number,
                        "zone_id": str(zone.id),
                        "confidence": confidence,
                    }
                ]
            },
        )
    )
    session.flush()


def _add_ble_event(
    context: ValidationContext,
    event_id: str,
    readings: list[dict[str, object]],
) -> None:
    session = context["session"]
    asset = context["asset"]
    tag = context["tag"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    assert isinstance(tag, Tag)
    session.add(
        BleEvent(
            tag_id=tag.id,
            asset_id=asset.id,
            event_id=event_id,
            timestamp=datetime.now(UTC),
            readings=readings,
            raw_payload={"readings": readings},
        )
    )
    session.flush()


def test_valid_camera_payload(validation_context: ValidationContext) -> None:
    response = validation_context["client"].post(
        "/api/v1/events/camera",
        json=_camera_payload(validation_context, f"validation-camera-{uuid4()}"),
    )
    assert response.status_code == 201


def test_malformed_camera_payload(validation_context: ValidationContext) -> None:
    response = validation_context["client"].post(
        "/api/v1/events/camera",
        json={"event_id": "malformed"},
    )
    assert response.status_code == 422


def test_duplicate_event_idempotency(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    event_id = f"validation-duplicate-{uuid4()}"
    payload = _camera_payload(context, event_id)

    first = context["client"].post("/api/v1/events/camera", json=payload)
    second = context["client"].post("/api/v1/events/camera", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert session.scalar(
        select(func.count()).select_from(CameraEvent).where(CameraEvent.event_id == event_id)
    ) == 1


def test_unknown_identifier(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    event_id = f"validation-unknown-{uuid4()}"
    payload = _camera_payload(context, event_id)
    payload["detections"] = [
        {"asset_identifier": "NOT-A-REAL-ASSET", "confidence": 0.2}
    ]

    response = context["client"].post("/api/v1/events/camera", json=payload)

    assert response.status_code == 201
    event = session.scalar(select(CameraEvent).where(CameraEvent.event_id == event_id))
    assert event is not None
    assert event.unknown_asset is True
    assert event.raw_payload["detections"][0]["asset_id"] is None


def test_two_gateway_agreement(validation_context: ValidationContext) -> None:
    context = validation_context
    _add_camera_event(context, f"validation-agree-camera-{uuid4()}", context["zone_a"], 0.98)
    _add_ble_event(
        context,
        f"validation-agree-ble-{uuid4()}",
        _zone_readings(context, context["zone_a"]),
    )

    result = run_fusion(str(context["asset"].id), context["session"])

    decision = context["session"].scalar(select(FusionDecision))
    assert result["decision_status"] == "confirmed"
    assert decision is not None
    assert decision.confidence_band == "high"
    assert decision.confidence >= 0.75


def test_single_gateway_no_position(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    _add_ble_event(
        context,
        f"validation-single-gateway-{uuid4()}",
        _zone_readings(context, context["zone_a"], (0,)),
    )

    result = run_fusion(str(context["asset"].id), session)

    assert result["status"] == "camera_silent"
    assert result["state_changed"] is False
    assert session.scalar(select(func.count()).select_from(LocationEstimate)) == 0
    assert session.scalar(select(func.count()).select_from(AssetCurrentState)) == 0


def test_sensor_silence_is_not_an_ingestible_ble_event(
    validation_context: ValidationContext,
) -> None:
    context = validation_context
    session = context["session"]
    event_id = f"validation-empty-ble-{uuid4()}"

    response = context["client"].post(
        "/api/v1/events/ble",
        json=_ble_payload(context, event_id, []),
    )
    result = run_fusion(str(context["asset"].id), session)

    event = session.scalar(select(BleEvent).where(BleEvent.event_id == event_id))
    assert response.status_code == 422
    assert event is None
    assert result["status"] == "camera_silent"
    assert result["state_changed"] is False
    assert session.scalar(select(func.count()).select_from(LocationEstimate)) == 0
    assert session.scalar(select(func.count()).select_from(AssetCurrentState)) == 0


def _confidence_for_conflict(
    camera_confidence: float,
    ble_quality: float,
) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return compute_confidence(
        {
            "camera_events": [
                {"zone_id": "ward-a", "confidence": camera_confidence, "timestamp": now}
            ],
            "ble_events": [
                {
                    "zone_id": "ward-b",
                    "ble_quality": ble_quality,
                    "timestamp": now,
                    "gateway_count": 4,
                }
            ],
            "zones": {},
        }
    )


def test_camera_ble_conflict_high_score() -> None:
    result = _confidence_for_conflict(1.0, 1.0)
    assert result["decision_status"] == "sensor_disagreement"
    assert result["confidence"] == 0.5
    assert result["confidence_breakdown"]["conflict_penalty"] == 0.3


def test_camera_ble_conflict_low_score() -> None:
    result = _confidence_for_conflict(0.1, 0.1)
    assert result["decision_status"] == "sensor_disagreement"
    assert result["confidence"] < 0.25


def test_camera_silent_no_state_change(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    asset = context["asset"]
    zone = context["zone_a"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    state = AssetCurrentState(
        asset_id=asset.id,
        zone_id=zone.id,
        confidence_band="medium",
        decision_status="confirmed",
    )
    location = LocationEstimate(
        asset_id=asset.id,
        x=20,
        y=20,
        zone_id=zone.id,
        gateway_count=2,
        ble_quality=0.8,
        method="wcl_zone_level",
    )
    session.add_all([state, location])
    session.flush()
    old_status = asset.operational_status
    old_band = state.confidence_band
    old_zone = state.zone_id
    old_coordinates = (location.x, location.y, location.zone_id)
    _add_ble_event(
        context,
        f"validation-camera-silent-{uuid4()}",
        _zone_readings(context, context["zone_b"], (2,)),
    )

    result = run_fusion(str(asset.id), session)

    session.refresh(state)
    session.refresh(asset)
    session.refresh(location)
    assert result["status"] == "camera_silent"
    assert result["state_changed"] is False
    assert state.zone_id == old_zone
    assert state.confidence_band == old_band
    assert asset.operational_status == old_status
    assert (location.x, location.y, location.zone_id) == old_coordinates


def test_heartbeat_no_detection(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    camera = context["camera"]
    counts_before = {
        model: session.scalar(select(func.count()).select_from(model))
        for model in (CameraEvent, BleEvent, LocationEstimate, AssetCurrentState)
    }

    response = context["client"].post(
        f"/api/v1/sensors/{camera.id}/heartbeat",
        json={"timestamp": datetime.now(UTC).isoformat()},
    )

    assert response.status_code == 200
    for model in (CameraEvent, BleEvent, LocationEstimate, AssetCurrentState):
        assert session.scalar(select(func.count()).select_from(model)) == counts_before[model]


def test_heartbeat_offline_timeout(validation_context: ValidationContext) -> None:
    context = validation_context
    camera = context["camera"]
    assert isinstance(camera, Camera)
    timestamp = datetime.now(UTC) - timedelta(seconds=2 * camera.heartbeat_timeout_s + 1)

    response = context["client"].post(
        f"/api/v1/sensors/{camera.id}/heartbeat",
        json={"timestamp": timestamp.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "offline"


def test_invalid_status_provenance_sensor(validation_context: ValidationContext) -> None:
    context = validation_context
    asset = context["asset"]

    response = context["client"].post(
        f"/api/v1/assets/{asset.id}/operational-status",
        json={
            "status": "available",
            "source": "sensor",
            "actor": "sensor-1",
            "reason": "sensor reported availability",
        },
    )

    assert response.status_code == 400


def test_invalid_status_provenance_bulk_import(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    asset = context["asset"]

    response = context["client"].post(
        f"/api/v1/assets/{asset.id}/operational-status",
        json={
            "status": "available",
            "source": "bulk_import",
            "actor": "importer",
            "reason": "import",
        },
    )
    assert response.status_code == 400

    with pytest.raises(DBAPIError):
        session.execute(
            text(
                """
                INSERT INTO assets (
                    code,
                    asset_type_id,
                    floor_id,
                    operational_status,
                    status_source,
                    status_actor,
                    status_reason
                )
                VALUES (
                    :code,
                    :asset_type_id,
                    :floor_id,
                    'available',
                    'bulk_import',
                    'importer',
                    'direct test'
                )
                """
            ),
            {
                "code": f"INVALID-BULK-{uuid4()}",
                "asset_type_id": asset.asset_type_id,
                "floor_id": asset.floor_id,
            },
        )
    session.rollback()
    assert session.scalar(
        select(func.count()).select_from(Asset).where(Asset.status_source == "bulk_import")
    ) == 0


def test_status_expiry(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    asset = context["asset"]
    asset.status_stale_after = datetime.now(UTC) - timedelta(minutes=1)
    session.flush()
    session.add(
        ParLevel(
            zone_id=context["zone_a"].id,
            asset_type_id=context["asset_type"].id,
            par_count=1,
        )
    )
    session.flush()

    assert run_status_expiry_sweep(session) == 1
    session.refresh(asset)
    assert asset.operational_status == "status_unknown"
    assert asset.status_stale_after is None
    assert asset.operational_status != "available"
    assert session.scalar(
        select(func.count()).select_from(AssetStatusHistory).where(
            AssetStatusHistory.asset_id == asset.id,
            AssetStatusHistory.status == "status_unknown",
        )
    ) == 1
    inventory = context["client"].get("/api/v1/inventory")
    row = next(
        item
        for item in inventory.json()
        if item["zone_name"] == context["zone_a"].name
        and item["asset_type_name"] == context["asset_type"].name
    )
    assert row["usable_count"] == 0


def test_usable_count_exclusion(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    asset = context["asset"]
    zone = context["zone_a"]
    asset.status_stale_after = datetime.now(UTC) - timedelta(minutes=1)
    session.add(
        ParLevel(
            zone_id=zone.id,
            asset_type_id=context["asset_type"].id,
            par_count=1,
        )
    )
    session.flush()

    response = context["client"].get("/api/v1/inventory")
    row = next(
        item
        for item in response.json()
        if item["zone_name"] == zone.name
        and item["asset_type_name"] == context["asset_type"].name
    )

    assert row["usable_count"] == 0
    assert row["status"] == "deficit"
    assert row["deficit_count"] == 1


def test_no_prohibited_terms_in_alerts(validation_context: ValidationContext) -> None:
    context = validation_context
    session = context["session"]
    zone = context["zone_a"]
    asset_type = context["asset_type"]
    session.add(
        ParLevel(
            zone_id=zone.id,
            asset_type_id=asset_type.id,
            par_count=5,
        )
    )
    session.flush()

    reconcile_response = context["client"].post("/api/v1/alerts/reconcile")
    assert reconcile_response.status_code == 200
    response = context["client"].get("/api/v1/alerts", params={"status": "open"})

    assert response.status_code == 200
    matching_alert = next(
        alert
        for alert in response.json()
        if alert["zone_id"] == str(zone.id)
        and alert["asset_type_id"] == str(asset_type.id)
    )
    prohibited = ["hoarding", "hoarder", "lazy", "negligent"]
    title_message = f"{matching_alert['title']} {matching_alert['message']}".casefold()
    assert not any(term in title_message for term in prohibited)
    stored_alert = session.get(Alert, UUID(matching_alert["id"]))
    assert stored_alert is not None
    assert stored_alert.title == matching_alert["title"]
    assert stored_alert.message == matching_alert["message"]


def test_deterministic_repeatability(validation_context: ValidationContext) -> None:
    context = validation_context
    _add_camera_event(
        context,
        f"validation-repeat-camera-{uuid4()}",
        context["zone_a"],
        0.91,
    )
    _add_ble_event(
        context,
        f"validation-repeat-ble-{uuid4()}",
        _zone_readings(context, context["zone_a"]),
    )

    session = context["session"]
    asset_id = context["asset"].id
    run_fusion(str(asset_id), session)
    first_decision = session.scalar(
        select(FusionDecision)
        .where(FusionDecision.asset_id == asset_id)
        .order_by(FusionDecision.created_at.desc())
        .limit(1)
    )
    assert first_decision is not None
    first_confidence = first_decision.confidence
    first_decision_id = first_decision.id

    run_fusion(str(asset_id), session)
    second_decision = session.scalar(
        select(FusionDecision)
        .where(
            FusionDecision.asset_id == asset_id,
            FusionDecision.id != first_decision_id,
        )
        .order_by(FusionDecision.created_at.desc())
        .limit(1)
    )
    assert second_decision is not None
    assert round(first_confidence, 2) == round(second_decision.confidence, 2)


def test_forecast_zero_demand() -> None:
    response = TestClient(app).get(
        "/api/v1/forecast",
        params={
            "demand_count": 0,
        },
    )

    assert response.status_code == 200
    assert response.json()["indicator"] == 0
    assert response.json()["band"] == "low"


def test_forecast_shortage() -> None:
    response = TestClient(app).get(
        "/api/v1/forecast",
        params={
            "demand_count": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["indicator"] > 0
    assert body["band"] in {"low", "moderate", "high", "critical"}
