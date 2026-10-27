from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    Asset,
    AssetCurrentState,
    BleEvent,
    Camera,
    CameraEvent,
    CoverageFigure,
    FusionDecision,
    Gateway,
    LocationEstimate,
    MovementHistory,
    Tag,
    Zone,
)
from app.services.confidence import compute_confidence
from app.services.localization import weighted_centroid_localization

EVIDENCE_WINDOW = timedelta(minutes=30)


def _camera_evidence_for_asset(
    event: CameraEvent,
    asset_id: UUID,
) -> list[dict[str, Any]]:
    if event.asset_id == asset_id:
        return [
            {
                "zone_id": str(event.zone_id) if event.zone_id else None,
                "confidence": event.confidence or 0.0,
                "timestamp": event.timestamp,
                "event_id": event.event_id,
            }
        ]

    detections = event.raw_payload.get("detections", [])
    return [
        {
            "zone_id": detection.get("zone_id"),
            "confidence": detection.get("confidence", 0.0),
            "timestamp": event.timestamp,
            "event_id": event.event_id,
        }
        for detection in detections
        if detection.get("asset_id") == str(asset_id)
    ]


def _bounds(polygon: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _zones_are_adjacent(left: Zone, right: Zone) -> bool:
    left_polygon = left.polygon_json
    right_polygon = right.polygon_json
    if len(left_polygon) < 3 or len(right_polygon) < 3:
        return False

    left_min_x, left_min_y, left_max_x, left_max_y = _bounds(left_polygon)
    right_min_x, right_min_y, right_max_x, right_max_y = _bounds(right_polygon)
    x_gap = max(left_min_x - right_max_x, right_min_x - left_max_x, 0.0)
    y_gap = max(left_min_y - right_max_y, right_min_y - left_max_y, 0.0)
    return x_gap == 0 and y_gap == 0


def _coverage_zone_ids(camera: Camera) -> list[str]:
    if not isinstance(camera.coverage_zone_ids, list):
        return []
    return [str(zone_id) for zone_id in camera.coverage_zone_ids]


def _record_camera_coverage(
    db: Session,
    cameras: list[Camera],
    zones_by_id: dict[str, Zone],
    now: datetime,
    window_start: datetime,
    zone_id: UUID,
) -> tuple[float, datetime | None]:
    figures: list[CoverageFigure] = []
    covered_camera_seen_times: list[datetime] = []
    for camera in cameras:
        is_recent = camera.last_seen_at is not None and camera.last_seen_at >= window_start
        percent = 100.0 if is_recent else 0.0
        camera_zone_ids = [
            candidate_id
            for candidate_id in _coverage_zone_ids(camera)
            if candidate_id == str(zone_id)
        ]
        for camera_zone_id in camera_zone_ids:
            zone = zones_by_id.get(camera_zone_id)
            if zone is not None:
                figures.append(
                    CoverageFigure(
                        camera_id=camera.id,
                        zone_id=zone.id,
                        coverage_percent=percent,
                        computed_at=now,
                    )
                )
                if camera.last_seen_at is not None:
                    covered_camera_seen_times.append(camera.last_seen_at)

    if not figures:
        zone = zones_by_id.get(str(zone_id))
        if zone is not None:
            figures.append(
                CoverageFigure(
                    camera_id=None,
                    zone_id=zone.id,
                    coverage_percent=0.0,
                    computed_at=now,
                )
            )

    if figures:
        db.add_all(figures)
        db.flush()
        coverage = round(
            sum(figure.coverage_percent for figure in figures) / len(figures),
            2,
        )
        return coverage, max(covered_camera_seen_times, default=None)
    return 0.0, None


def run_fusion(asset_id: str, db: Session) -> dict[str, Any]:
    try:
        asset_uuid = UUID(asset_id)
    except ValueError as error:
        raise ValueError(f"Invalid asset ID: {asset_id}") from error

    asset = db.get(Asset, asset_uuid)
    if asset is None:
        raise LookupError(f"Asset not found: {asset_id}")

    now = datetime.now(UTC)
    window_start = now - EVIDENCE_WINDOW

    recent_camera_events = db.scalars(
        select(CameraEvent)
        .where(CameraEvent.timestamp >= window_start)
        .order_by(CameraEvent.timestamp)
    ).all()
    camera_evidence = [
        detection
        for event in recent_camera_events
        for detection in _camera_evidence_for_asset(event, asset_uuid)
    ]

    asset_tag_ids = db.scalars(
        select(Tag.id).where(Tag.asset_id == asset_uuid)
    ).all()
    ble_query = select(BleEvent).where(BleEvent.timestamp >= window_start)
    if asset_tag_ids:
        ble_query = ble_query.where(
            or_(
                BleEvent.asset_id == asset_uuid,
                BleEvent.tag_id.in_(asset_tag_ids),
            )
        )
    else:
        ble_query = ble_query.where(BleEvent.asset_id == asset_uuid)
    recent_ble_events = db.scalars(
        ble_query.order_by(BleEvent.timestamp.desc())
    ).all()

    zones = db.scalars(
        select(Zone).where(Zone.floor_id == asset.floor_id)
    ).all()
    zones_by_id = {str(zone.id): zone for zone in zones}
    adjacency_map = {
        str(zone.id): {
            "adjacent_zone_ids": [
                str(other.id)
                for other in zones
                if other.id != zone.id and _zones_are_adjacent(zone, other)
            ]
        }
        for zone in zones
    }

    ble_evidence: list[dict[str, Any]] = []
    localization: dict[str, Any] | None = None
    distinct_gateway_count = 0
    if recent_ble_events:
        latest_ble_event = recent_ble_events[0]
        gateways = db.scalars(
            select(Gateway).where(Gateway.floor_id == asset.floor_id)
        ).all()
        gateway_positions: dict[str, Any] = {
            str(gateway.id): {"x": gateway.x, "y": gateway.y}
            for gateway in gateways
        }
        gateway_positions["zones"] = {
            zone_id: zone.polygon_json for zone_id, zone in zones_by_id.items()
        }

        readings = []
        for reading in latest_ble_event.readings:
            gateway_id = str(reading.get("gateway_id"))
            if gateway_id == "zones" or gateway_id not in gateway_positions:
                continue
            normalized_reading = dict(reading)
            normalized_reading.setdefault("timestamp", latest_ble_event.timestamp.isoformat())
            readings.append(normalized_reading)

        distinct_gateway_count = len(
            {str(reading["gateway_id"]) for reading in readings}
        )
        localization = weighted_centroid_localization(readings, gateway_positions)
        ble_evidence.append(
            {
                "zone_id": localization["zone_id"],
                "ble_quality": localization["ble_quality"],
                "timestamp": latest_ble_event.timestamp,
                "gateway_count": localization["gateway_count"],
                "distinct_gateway_count": distinct_gateway_count,
                "rssi_spread": localization["rssi_spread"],
                "calibration": localization["calibration"],
                "event_id": latest_ble_event.event_id,
            }
        )

    evidence = {
        "camera_events": camera_evidence,
        "ble_events": ble_evidence,
        "asset_id": asset_id,
        "zones": adjacency_map,
    }

    cameras = db.scalars(
        select(Camera).where(Camera.floor_id == asset.floor_id)
    ).all()
    has_qualifying_ble_position = (
        not camera_evidence
        and bool(ble_evidence)
        and distinct_gateway_count >= 2
        and localization is not None
        and localization["zone_id"] is not None
    )
    if not camera_evidence and not has_qualifying_ble_position:
        state = db.scalar(
            select(AssetCurrentState).where(AssetCurrentState.asset_id == asset_uuid)
        )
        location_zone_id = (
            state.zone_id
            if state is not None and state.zone_id is not None
            else asset.current_zone_id
        )
        if location_zone_id is not None:
            coverage, camera_last_seen = _record_camera_coverage(
                db,
                cameras,
                zones_by_id,
                now,
                window_start,
                UUID(str(location_zone_id)),
            )
        else:
            coverage, camera_last_seen = 0.0, None
        db.commit()
        return {
            "status": "camera_silent",
            "state_changed": False,
            "coverage": coverage,
            "camera_last_seen": camera_last_seen,
            "gateway_count": (
                localization["gateway_count"] if localization is not None else 0
            ),
            "rssi_spread": (
                localization["rssi_spread"] if localization is not None else 0.0
            ),
            "calibration": (
                localization["calibration"]
                if localization is not None
                else {"note": "site-simulated"}
            ),
            "zone_id": None,
        }

    confidence_result = compute_confidence(evidence)
    camera_zone_id = camera_evidence[-1]["zone_id"] if camera_evidence else None
    ble_zone_id = ble_evidence[-1]["zone_id"] if ble_evidence else None
    if confidence_result["decision_status"] == "sensor_disagreement":
        camera_zone_name = (
            zones_by_id[camera_zone_id].name
            if camera_zone_id in zones_by_id
            else camera_zone_id or "unknown zone"
        )
        ble_zone_name = (
            zones_by_id[ble_zone_id].name
            if ble_zone_id in zones_by_id
            else ble_zone_id or "unknown zone"
        )
        partial_agreement = (
            " across adjacent zones (partial zone agreement)"
            if confidence_result["confidence_breakdown"]["zone_agreement"] == 0.5
            else ""
        )
        confidence_result["reason"] = (
            f"Sensor disagreement{partial_agreement}: camera reports "
            f"{camera_zone_name}, BLE reports {ble_zone_name} "
            f"(confidence {confidence_result['confidence']:.2f}, "
            f"{confidence_result['confidence_band']} band)"
        )
    fusion_decision = FusionDecision(
        asset_id=asset_uuid,
        decision_status=confidence_result["decision_status"],
        confidence=confidence_result["confidence"],
        confidence_band=confidence_result["confidence_band"],
        confidence_breakdown=confidence_result["confidence_breakdown"],
        calibration_info=(
            localization["calibration"]
            if localization is not None
            else {"note": "site-simulated"}
        ),
        evidence_links=[
            {
                "source": "camera",
                "event_id": item["event_id"],
                "href": f"/api/v1/events/{item['event_id']}",
            }
            for item in camera_evidence
        ]
        + [
            {
                "source": "ble",
                "event_id": item["event_id"],
                "href": f"/api/v1/events/{item['event_id']}",
            }
            for item in ble_evidence
        ],
        camera_zone_id=UUID(camera_zone_id) if camera_zone_id else None,
        ble_zone_id=UUID(ble_zone_id) if ble_zone_id else None,
        reason=confidence_result["reason"],
        evidence_window_start=window_start,
        evidence_window_end=now,
    )
    db.add(fusion_decision)
    db.flush()

    fused_zone_id = camera_zone_id or ble_zone_id
    current_state = db.scalar(
        select(AssetCurrentState).where(AssetCurrentState.asset_id == asset_uuid)
    )
    previous_zone_id = (
        current_state.zone_id
        if current_state is not None
        else asset.current_zone_id
    )
    is_sensor_disagreement = (
        confidence_result["decision_status"] == "sensor_disagreement"
    )
    review_alert = db.scalar(
        select(Alert).where(
            Alert.asset_id == asset_uuid,
            Alert.alert_type == "sensor_disagreement",
            Alert.status == "open",
        )
    )
    if is_sensor_disagreement and review_alert is None:
        review_alert = Alert(
            alert_type="sensor_disagreement",
            asset_id=asset_uuid,
            zone_id=UUID(camera_zone_id or ble_zone_id),
            asset_type_id=asset.asset_type_id,
            count=0,
            par_count=0,
            severity="medium",
            title="Location review needed",
            message="Camera and BLE evidence conflict; review the linked observations.",
            status="open",
        )
        db.add(review_alert)
    elif not is_sensor_disagreement and review_alert is not None:
        review_alert.status = "resolved"
    if current_state is None:
        current_state = AssetCurrentState(
            asset_id=asset_uuid,
            zone_id=(
                previous_zone_id
                if is_sensor_disagreement
                else (UUID(fused_zone_id) if fused_zone_id else None)
            ),
            confidence_band=confidence_result["confidence_band"],
            decision_status=confidence_result["decision_status"],
            last_fusion_decision_id=fusion_decision.id,
            updated_at=now,
        )
        db.add(current_state)
    else:
        if not is_sensor_disagreement:
            current_state.zone_id = UUID(fused_zone_id) if fused_zone_id else None
        current_state.confidence_band = confidence_result["confidence_band"]
        current_state.decision_status = confidence_result["decision_status"]
        current_state.last_fusion_decision_id = fusion_decision.id
        current_state.updated_at = now

    if (
        not is_sensor_disagreement
        and fused_zone_id
        and fused_zone_id != (str(previous_zone_id) if previous_zone_id else None)
    ):
        db.add(
            MovementHistory(
                asset_id=asset_uuid,
                from_zone_id=previous_zone_id,
                to_zone_id=UUID(fused_zone_id),
                fusion_decision_id=fusion_decision.id,
            )
        )

    if (
        localization is not None
        and localization["x"] is not None
        and localization["zone_id"] is not None
    ):
        db.add(
            LocationEstimate(
                asset_id=asset_uuid,
                fusion_decision_id=fusion_decision.id,
                x=localization["x"],
                y=localization["y"],
                zone_id=UUID(localization["zone_id"]),
                gateway_count=localization["gateway_count"],
                ble_quality=localization["ble_quality"],
                method=localization["method"],
            )
        )

    asset.last_fusion_at = now
    if (
        confidence_result["decision_status"] != "sensor_disagreement"
        and fused_zone_id is not None
    ):
        asset.current_zone_id = UUID(fused_zone_id)
        asset.updated_at = now
    db.commit()

    return {
        "status": "fused",
        "decision_status": confidence_result["decision_status"],
        "review_state": (
            "needs_review"
            if confidence_result["decision_status"] == "sensor_disagreement"
            else None
        ),
        "review_alert_id": str(review_alert.id) if review_alert is not None else None,
        "confidence_band": confidence_result["confidence_band"],
        "zone_id": (
            str(previous_zone_id)
            if is_sensor_disagreement and previous_zone_id is not None
            else None
            if is_sensor_disagreement
            else fused_zone_id
        ),
        "camera_zone_id": camera_zone_id,
        "ble_zone_id": ble_zone_id,
        "reason": confidence_result["reason"],
        "evidence_links": fusion_decision.evidence_links,
        "gateway_count": (
            localization["gateway_count"] if localization is not None else 0
        ),
        "rssi_spread": (
            localization["rssi_spread"] if localization is not None else 0.0
        ),
        "calibration": (
            localization["calibration"]
            if localization is not None
            else {"note": "site-simulated"}
        ),
        "state_changed": True,
    }
