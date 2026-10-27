from datetime import UTC, datetime
from typing import Any, TypedDict


class ConfidenceBreakdown(TypedDict):
    camera_confidence: float
    ble_quality: float
    zone_agreement: float
    freshness: float
    coverage: float
    conflict_penalty: float
    stale_penalty: float
    gateway_count: int
    rssi_spread: float


class ConfidenceResult(TypedDict):
    confidence: float
    confidence_band: str
    decision_status: str
    confidence_breakdown: ConfidenceBreakdown
    reason: str


def _timestamp(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _band_for_score(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.55:
        return "medium"
    if score >= 0.30:
        return "low"
    return "stale"


def compute_confidence(evidence: dict[str, Any]) -> ConfidenceResult:
    """Combine available sensor evidence into an uncalibrated weighted score."""
    camera_events = evidence.get("camera_events", [])
    ble_events = evidence.get("ble_events", [])
    zones = evidence.get("zones", {})

    camera_confidence = max(
        (float(event["confidence"]) for event in camera_events),
        default=0.0,
    )
    ble_quality = max(
        (float(event["ble_quality"]) for event in ble_events),
        default=0.0,
    )
    latest_ble = ble_events[-1] if ble_events else {}

    camera_zone = camera_events[-1].get("zone_id") if camera_events else None
    ble_zone = ble_events[-1].get("zone_id") if ble_events else None

    if camera_zone is not None and ble_zone is not None:
        if camera_zone == ble_zone:
            zone_agreement = 1.0
        elif ble_zone in zones.get(camera_zone, {}).get("adjacent_zone_ids", []):
            zone_agreement = 0.5
        elif camera_zone in zones.get(ble_zone, {}).get("adjacent_zone_ids", []):
            zone_agreement = 0.5
        else:
            zone_agreement = 0.0
    else:
        zone_agreement = 0.0

    timestamps = [
        _timestamp(event["timestamp"])
        for event in [*camera_events, *ble_events]
        if event.get("timestamp") is not None
    ]
    now = datetime.now(UTC)
    ages_seconds = [max(0.0, (now - timestamp).total_seconds()) for timestamp in timestamps]
    if ages_seconds:
        max_age_seconds = max(ages_seconds)
        if max_age_seconds < 5 * 60:
            freshness = 1.0
        else:
            freshness = max(0.0, (30 * 60 - max_age_seconds) / (25 * 60))
    else:
        freshness = 0.0

    has_camera = bool(camera_events)
    has_ble = bool(ble_events)
    if has_camera and has_ble:
        coverage = 1.0
    elif has_camera or has_ble:
        coverage = 0.7
    else:
        coverage = 0.4

    zones_disagree = (
        has_camera
        and has_ble
        and camera_zone is not None
        and ble_zone is not None
        and camera_zone != ble_zone
    )
    conflict_penalty = 0.3 if zones_disagree else 0.0
    stale_penalty = 0.2 if any(age > 15 * 60 for age in ages_seconds) else 0.0

    score = (
        camera_confidence * 0.25
        + ble_quality * 0.25
        + zone_agreement * 0.2
        + freshness * 0.15
        + coverage * 0.15
        - conflict_penalty
        - stale_penalty
    )
    score = min(1.0, max(0.0, score))

    confidence_band = _band_for_score(score)
    if has_camera != has_ble and confidence_band == "high":
        confidence_band = "medium"

    if zones_disagree:
        decision_status = "sensor_disagreement"
        if zone_agreement == 0.5:
            reason = (
                f"Sensor disagreement across adjacent zones: camera reports {camera_zone}, "
                f"BLE reports {ble_zone} (partial zone agreement, confidence {score:.2f}, "
                f"{confidence_band} band)"
            )
        else:
            reason = (
                f"Sensor disagreement: camera reports {camera_zone}, "
                f"BLE reports {ble_zone} (confidence {score:.2f}, {confidence_band} band)"
            )
    elif stale_penalty > 0 and score < 0.30:
        decision_status = "stale"
        reason = f"Evidence is stale (confidence {score:.2f}, stale band)"
    elif (
        has_camera
        and has_ble
        and camera_zone is not None
        and camera_zone == ble_zone
    ):
        decision_status = "confirmed"
        reason = (
            f"Camera and BLE agree on {camera_zone} "
            f"(confidence {score:.2f}, {confidence_band} band)"
        )
    elif has_camera and has_ble:
        decision_status = "confirmed"
        reason = (
            "Camera and BLE evidence available, but zone agreement is unavailable "
            f"(confidence {score:.2f}, {confidence_band} band)"
        )
    elif has_camera or has_ble:
        modality = "Camera" if has_camera else "BLE"
        reason = (
            f"{modality} evidence available "
            f"(confidence {score:.2f}, {confidence_band} band)"
        )
        decision_status = "confirmed"
    else:
        decision_status = "unknown"
        reason = "No sensor evidence available"

    breakdown: ConfidenceBreakdown = {
        "camera_confidence": round(camera_confidence, 2),
        "ble_quality": round(ble_quality, 2),
        "zone_agreement": round(zone_agreement, 2),
        "freshness": round(freshness, 2),
        "coverage": round(coverage, 2),
        "conflict_penalty": round(conflict_penalty, 2),
        "stale_penalty": round(stale_penalty, 2),
        "gateway_count": int(latest_ble.get("gateway_count", 0)),
        "rssi_spread": round(float(latest_ble.get("rssi_spread", 0.0)), 2),
    }
    return {
        "confidence": round(score, 2),
        "confidence_band": confidence_band,
        "decision_status": decision_status,
        "confidence_breakdown": breakdown,
        "reason": reason,
    }
