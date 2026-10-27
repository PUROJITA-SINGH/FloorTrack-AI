from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import engine
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
    FusionDecision,
    Gateway,
    LocationEstimate,
    MovementHistory,
    Tag,
    Zone,
)
from app.services.fusion import run_fusion


@pytest.fixture
def fusion_context() -> Iterator[dict[str, object]]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    facility = Facility(name="Fusion test facility")
    session.add(facility)
    session.flush()
    floor = Floor(facility_id=facility.id, name="Fusion floor", floor_number=1)
    asset_type = AssetType(name="Fusion pump")
    session.add_all([floor, asset_type])
    session.flush()

    first_zone = Zone(
        floor_id=floor.id,
        name="Ward A",
        zone_type="ward",
        polygon_json=[[0, 0], [40, 0], [40, 40], [0, 40]],
    )
    second_zone = Zone(
        floor_id=floor.id,
        name="Ward B",
        zone_type="ward",
        polygon_json=[[60, 60], [100, 60], [100, 100], [60, 100]],
    )
    session.add_all([first_zone, second_zone])
    session.flush()

    asset = Asset(
        code="FUSION-TEST",
        asset_type_id=asset_type.id,
        floor_id=floor.id,
        operational_status="status_unknown",
        status_source="workflow_adapter",
        status_actor="test",
        status_reason="fixture",
    )
    camera = Camera(
        floor_id=floor.id,
        name="Fusion camera",
        coverage_zone_ids=[str(first_zone.id)],
        heartbeat_timeout_s=60,
        status="online",
        last_seen_at=datetime.now(UTC),
    )
    gateway = Gateway(
        floor_id=floor.id,
        name="Fusion gateway",
        x=20,
        y=20,
        heartbeat_timeout_s=60,
        status="online",
    )
    session.add_all([asset, camera, gateway])
    session.flush()
    tag = Tag(asset_id=asset.id, tag_type="ble", tag_value="FUSION-TAG")
    session.add(tag)
    session.flush()

    try:
        yield {
            "session": session,
            "asset": asset,
            "camera": camera,
            "gateway": gateway,
            "tag": tag,
            "zone": first_zone,
            "other_zone": second_zone,
        }
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_run_fusion_returns_no_evidence_without_state_changes(
    fusion_context: dict[str, object],
) -> None:
    session = fusion_context["session"]
    asset = fusion_context["asset"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)

    result = run_fusion(str(asset.id), session)

    assert result["status"] == "camera_silent"
    assert result["state_changed"] is False
    assert result["coverage"] == 0.0
    assert result["camera_last_seen"] is None
    assert result["gateway_count"] == 0
    assert result["rssi_spread"] == 0.0
    assert result["calibration"]["note"] == "site-simulated"
    assert session.scalar(select(func.count()).select_from(FusionDecision)) == 0
    assert session.scalar(select(func.count()).select_from(AssetCurrentState)) == 0
    assert session.scalar(select(func.count()).select_from(CoverageFigure)) == 0


def test_camera_silent_without_known_zone_does_not_use_unrelated_coverage(
    fusion_context: dict[str, object],
) -> None:
    session = fusion_context["session"]
    asset = fusion_context["asset"]
    camera = fusion_context["camera"]
    tag = fusion_context["tag"]
    zone = fusion_context["zone"]
    gateway = fusion_context["gateway"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    assert isinstance(camera, Camera)
    assert isinstance(tag, Tag)
    assert isinstance(zone, Zone)
    assert isinstance(gateway, Gateway)

    session.add(
        BleEvent(
            tag_id=tag.id,
            asset_id=asset.id,
            event_id="fusion-camera-silent-ble",
            timestamp=datetime.now(UTC),
            readings=[
                {"gateway_id": str(gateway.id), "rssi": -50},
                {"gateway_id": str(gateway.id), "rssi": -55},
            ],
            raw_payload={},
        )
    )
    session.flush()

    result = run_fusion(str(asset.id), session)

    assert result["status"] == "camera_silent"
    assert result["state_changed"] is False
    assert result["coverage"] == 0.0
    assert result["camera_last_seen"] is None
    assert result["gateway_count"] == 1
    assert result["rssi_spread"] == 5.0
    assert result["calibration"]["note"] == "site-simulated"
    assert session.scalar(select(func.count()).select_from(CoverageFigure)) == 0
    assert session.scalar(select(func.count()).select_from(FusionDecision)) == 0
    assert session.scalar(select(func.count()).select_from(AssetCurrentState)) == 0
    assert session.scalar(select(func.count()).select_from(MovementHistory)) == 0
    assert session.scalar(select(func.count()).select_from(LocationEstimate)) == 0
    session.refresh(asset)
    assert asset.last_fusion_at is None
    assert asset.operational_status == "status_unknown"
    session.refresh(camera)
    assert camera.status == "online"


def test_camera_silent_returns_zero_for_zone_without_covering_camera(
    fusion_context: dict[str, object],
) -> None:
    session = fusion_context["session"]
    asset = fusion_context["asset"]
    tag = fusion_context["tag"]
    gateway = fusion_context["gateway"]
    other_zone = fusion_context["other_zone"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    assert isinstance(tag, Tag)
    assert isinstance(gateway, Gateway)
    assert isinstance(other_zone, Zone)

    session.add(
        AssetCurrentState(
            asset_id=asset.id,
            zone_id=other_zone.id,
            confidence_band="low",
            decision_status="confirmed",
        )
    )
    session.add(
        BleEvent(
            tag_id=tag.id,
            asset_id=asset.id,
            event_id="fusion-silent-uncovered-zone",
            timestamp=datetime.now(UTC),
            readings=[
                {"gateway_id": str(gateway.id), "rssi": -50},
                {"gateway_id": str(gateway.id), "rssi": -55},
            ],
            raw_payload={},
        )
    )
    session.flush()

    result = run_fusion(str(asset.id), session)

    assert result["status"] == "camera_silent"
    assert result["coverage"] == 0.0
    assert result["camera_last_seen"] is None
    figure = session.scalar(
        select(CoverageFigure).where(CoverageFigure.zone_id == other_zone.id)
    )
    assert figure is not None
    assert figure.camera_id is None
    assert figure.coverage_percent == 0.0
    assert session.scalar(select(func.count()).select_from(FusionDecision)) == 0


def test_ble_only_camera_silence_preserves_state_and_returns_zone_coverage(
    fusion_context: dict[str, object],
) -> None:
    session = fusion_context["session"]
    asset = fusion_context["asset"]
    camera = fusion_context["camera"]
    tag = fusion_context["tag"]
    zone = fusion_context["zone"]
    gateway = fusion_context["gateway"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    assert isinstance(camera, Camera)
    assert isinstance(tag, Tag)
    assert isinstance(zone, Zone)
    assert isinstance(gateway, Gateway)

    state = AssetCurrentState(
        asset_id=asset.id,
        zone_id=zone.id,
        confidence_band="medium",
        decision_status="confirmed",
    )
    session.add(state)
    session.flush()
    old_band = state.confidence_band
    old_decision_status = state.decision_status
    old_updated_at = state.updated_at
    old_operational_status = asset.operational_status

    session.add(
        BleEvent(
            tag_id=tag.id,
            asset_id=asset.id,
            event_id="fusion-ble-only-silent",
            timestamp=datetime.now(UTC),
            readings=[
                {"gateway_id": str(gateway.id), "rssi": -50},
                {"gateway_id": str(gateway.id), "rssi": -55},
            ],
            raw_payload={},
        )
    )
    session.flush()

    result = run_fusion(str(asset.id), session)

    session.refresh(state)
    session.refresh(asset)
    assert result["status"] == "camera_silent"
    assert result["state_changed"] is False
    assert result["coverage"] == 100.0
    assert result["camera_last_seen"] == camera.last_seen_at
    assert state.zone_id == zone.id
    assert state.confidence_band == old_band
    assert state.decision_status == old_decision_status
    assert state.updated_at == old_updated_at
    assert asset.operational_status == old_operational_status
    assert asset.last_fusion_at is None
    assert session.scalar(select(func.count()).select_from(FusionDecision)) == 0
    figures = session.scalars(
        select(CoverageFigure).where(CoverageFigure.zone_id == zone.id)
    ).all()
    assert len(figures) == 1
    assert figures[0].coverage_percent == 100.0


def test_ble_only_produces_position(
    fusion_context: dict[str, object],
) -> None:
    session = fusion_context["session"]
    asset = fusion_context["asset"]
    tag = fusion_context["tag"]
    gateway = fusion_context["gateway"]
    zone = fusion_context["zone"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    assert isinstance(tag, Tag)
    assert isinstance(gateway, Gateway)
    assert isinstance(zone, Zone)

    second_gateway = Gateway(
        floor_id=asset.floor_id,
        name="Second fusion gateway",
        x=25,
        y=25,
        heartbeat_timeout_s=60,
        status="online",
    )
    session.add(second_gateway)
    session.flush()
    session.add(
        BleEvent(
            tag_id=tag.id,
            asset_id=asset.id,
            event_id="fusion-ble-only-position",
            timestamp=datetime.now(UTC),
            readings=[
                {"gateway_id": str(gateway.id), "rssi": -50},
                {"gateway_id": str(second_gateway.id), "rssi": -55},
            ],
            raw_payload={},
        )
    )
    session.flush()

    result = run_fusion(str(asset.id), session)

    assert result["status"] == "fused"
    assert result["decision_status"] == "confirmed"
    assert result["zone_id"] == str(zone.id)
    assert result["confidence_band"] in {"medium", "low", "stale"}
    decision = session.scalar(select(FusionDecision))
    state = session.scalar(
        select(AssetCurrentState).where(AssetCurrentState.asset_id == asset.id)
    )
    location = session.scalar(select(LocationEstimate))
    assert decision is not None
    assert decision.camera_zone_id is None
    assert decision.ble_zone_id == zone.id
    assert state is not None
    assert state.zone_id == zone.id
    assert location is not None
    assert location.zone_id == zone.id


def test_fusion_conflict_does_not_advance(
    fusion_context: dict[str, object],
) -> None:
    session = fusion_context["session"]
    asset = fusion_context["asset"]
    camera = fusion_context["camera"]
    tag = fusion_context["tag"]
    gateway = fusion_context["gateway"]
    zone = fusion_context["zone"]
    other_zone = fusion_context["other_zone"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    assert isinstance(camera, Camera)
    assert isinstance(tag, Tag)
    assert isinstance(gateway, Gateway)
    assert isinstance(zone, Zone)
    assert isinstance(other_zone, Zone)

    second_gateway = Gateway(
        floor_id=asset.floor_id,
        name="Second conflict gateway",
        x=85,
        y=85,
        heartbeat_timeout_s=60,
        status="online",
    )
    asset.current_zone_id = other_zone.id
    state = AssetCurrentState(
        asset_id=asset.id,
        zone_id=other_zone.id,
        confidence_band="medium",
        decision_status="confirmed",
    )
    session.add_all(
        [
            second_gateway,
            state,
            CameraEvent(
                camera_id=camera.id,
                asset_id=asset.id,
                event_id="fusion-conflict-camera",
                timestamp=datetime.now(UTC),
                zone_id=zone.id,
                confidence=0.9,
                raw_payload={},
            ),
        ]
    )
    session.flush()
    session.add(
        BleEvent(
            tag_id=tag.id,
            asset_id=asset.id,
            event_id="fusion-conflict-ble",
            timestamp=datetime.now(UTC),
            readings=[
                {"gateway_id": str(gateway.id), "rssi": -100},
                {"gateway_id": str(second_gateway.id), "rssi": -40},
            ],
            raw_payload={},
        )
    )
    session.flush()
    previous_updated_at = state.updated_at

    result = run_fusion(str(asset.id), session)

    session.refresh(asset)
    session.refresh(state)
    decision = session.scalar(select(FusionDecision))
    assert result["status"] == "fused"
    assert result["decision_status"] == "sensor_disagreement"
    assert decision is not None
    assert decision.decision_status == "sensor_disagreement"
    assert decision.camera_zone_id == zone.id
    assert decision.ble_zone_id == other_zone.id
    assert "disagreement" in decision.reason.lower()
    assert decision.confidence_breakdown["conflict_penalty"] > 0
    assert state.zone_id == other_zone.id
    assert state.confidence_band == result["confidence_band"]
    assert state.decision_status == "sensor_disagreement"
    assert state.last_fusion_decision_id == decision.id
    assert state.updated_at != previous_updated_at
    assert asset.current_zone_id == other_zone.id
    assert session.scalar(select(func.count()).select_from(MovementHistory)) == 0


def test_fusion_writes_decision_and_location_state_only(
    fusion_context: dict[str, object],
) -> None:
    session = fusion_context["session"]
    asset = fusion_context["asset"]
    camera = fusion_context["camera"]
    zone = fusion_context["zone"]
    assert isinstance(session, Session)
    assert isinstance(asset, Asset)
    assert isinstance(camera, Camera)
    assert isinstance(zone, Zone)

    event_time = datetime.now(UTC) - timedelta(seconds=5)
    session.add(
        CameraEvent(
            camera_id=camera.id,
            asset_id=asset.id,
            event_id="fusion-camera-evidence",
            timestamp=event_time,
            zone_id=zone.id,
            confidence=0.85,
            raw_payload={},
        )
    )
    session.flush()

    result = run_fusion(str(asset.id), session)

    assert result["status"] == "fused"
    assert result["state_changed"] is True
    assert result["zone_id"] == str(zone.id)
    decision = session.scalar(select(FusionDecision))
    state = session.scalar(
        select(AssetCurrentState).where(AssetCurrentState.asset_id == asset.id)
    )
    assert decision is not None
    assert state is not None
    assert state.zone_id == zone.id
    assert state.last_fusion_decision_id == decision.id
    assert session.scalar(select(func.count()).select_from(MovementHistory)) == 1
    assert session.scalar(select(func.count()).select_from(LocationEstimate)) == 0
    session.refresh(asset)
    assert asset.last_fusion_at is not None
    assert asset.current_zone_id == zone.id
    assert asset.operational_status == "status_unknown"
