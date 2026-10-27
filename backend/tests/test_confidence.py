from datetime import UTC, datetime, timedelta

import pytest

from app.services.confidence import compute_confidence


def test_agreeing_camera_and_ble_produce_confirmed_score() -> None:
    now = datetime.now(UTC).isoformat()
    result = compute_confidence(
        {
            "camera_events": [{"zone_id": "ward-a", "confidence": 0.82, "timestamp": now}],
            "ble_events": [{"zone_id": "ward-a", "ble_quality": 0.8, "timestamp": now, "gateway_count": 3}],
            "asset_id": "asset-1",
            "zones": {},
        }
    )

    assert result["decision_status"] == "confirmed"
    assert result["confidence_band"] == "high"
    assert result["confidence"] == 0.91
    assert result["confidence_breakdown"]["zone_agreement"] == 1.0


def test_score_076_is_medium() -> None:
    now = datetime.now(UTC).isoformat()
    result = compute_confidence(
        {
            "camera_events": [
                {"zone_id": "ward-a", "confidence": 0.92, "timestamp": now}
            ],
            "ble_events": [
                {"zone_id": None, "ble_quality": 0.92, "timestamp": now}
            ],
            "zones": {},
        }
    )

    assert result["confidence"] == 0.76
    assert result["confidence_band"] == "medium"


def test_adjacent_zones_receive_partial_agreement() -> None:
    now = datetime.now(UTC).isoformat()
    result = compute_confidence(
        {
            "camera_events": [{"zone_id": "ward-a", "confidence": 0.8, "timestamp": now}],
            "ble_events": [{"zone_id": "corridor", "ble_quality": 0.7, "timestamp": now, "gateway_count": 2}],
            "zones": {"ward-a": {"adjacent_zone_ids": ["corridor"]}},
        }
    )
    assert result["confidence_breakdown"]["zone_agreement"] == 0.5
    assert result["decision_status"] == "sensor_disagreement"


def test_disagreement_applies_penalty_and_status() -> None:
    now = datetime.now(UTC).isoformat()
    result = compute_confidence(
        {
            "camera_events": [{"zone_id": "ward-a", "confidence": 0.9, "timestamp": now}],
            "ble_events": [{"zone_id": "ward-b", "ble_quality": 0.9, "timestamp": now, "gateway_count": 4}],
            "zones": {},
        }
    )
    assert result["confidence_breakdown"]["conflict_penalty"] == 0.3
    assert result["decision_status"] == "sensor_disagreement"
    assert "camera reports ward-a" in result["reason"]
    assert "BLE reports ward-b" in result["reason"]


def test_single_modality_band_is_capped_at_medium() -> None:
    now = datetime.now(UTC).isoformat()
    result = compute_confidence(
        {
            "camera_events": [{"zone_id": "ward-a", "confidence": 1.0, "timestamp": now}],
            "ble_events": [],
            "zones": {},
        }
    )
    assert result["confidence_band"] == "low"


def test_stale_evidence_penalty_and_decision() -> None:
    old_timestamp = (datetime.now(UTC) - timedelta(minutes=40)).isoformat()
    result = compute_confidence(
        {
            "camera_events": [{"zone_id": "ward-a", "confidence": 0.1, "timestamp": old_timestamp}],
            "ble_events": [],
            "zones": {},
        }
    )
    assert result["confidence_breakdown"]["freshness"] == 0.0
    assert result["confidence_breakdown"]["stale_penalty"] == 0.2
    assert result["decision_status"] == "stale"
    assert result["confidence_band"] == "stale"


def test_absent_evidence_is_unknown_with_zero_score() -> None:
    result = compute_confidence({"camera_events": [], "ble_events": [], "zones": {}})
    assert result["confidence"] == 0.06
    assert result["decision_status"] == "unknown"
    assert result["confidence_band"] == "stale"


def test_breakdown_and_confidence_are_rounded_to_two_decimals() -> None:
    now = datetime.now(UTC).isoformat()
    result = compute_confidence(
        {
            "camera_events": [{"zone_id": "ward-a", "confidence": 0.813, "timestamp": now}],
            "ble_events": [{"zone_id": "ward-a", "ble_quality": 0.777, "timestamp": now, "gateway_count": 2}],
            "zones": {},
        }
    )
    assert all(
        round(value, 2) == value
        for value in result["confidence_breakdown"].values()
    )
    assert round(result["confidence"], 2) == result["confidence"]
