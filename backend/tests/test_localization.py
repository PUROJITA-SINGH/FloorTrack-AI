import pytest

from datetime import UTC, datetime, timedelta

from app.services.localization import (
    compute_ble_quality,
    get_calibration_info,
    point_in_polygon,
    rssi_to_distance,
    weighted_centroid_localization,
)


def test_rssi_to_distance_defaults() -> None:
    assert rssi_to_distance(-59.0) == pytest.approx(1.0)
    assert rssi_to_distance(-69.0) == pytest.approx(3.1622776602)


def test_rssi_to_distance_custom_parameters() -> None:
    assert rssi_to_distance(-59.0, tx_power=-49.0, path_loss_exponent=2.0) == pytest.approx(
        3.1622776602
    )


def test_calibration_info_marks_constants_site_simulated() -> None:
    assert get_calibration_info() == {
        "tx_power": -59.0,
        "path_loss_exponent": 2.0,
        "note": "site-simulated",
        "gateway_coordinates": {},
    }


def test_point_in_polygon_uses_ray_casting() -> None:
    polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert point_in_polygon(5, 5, polygon)
    assert not point_in_polygon(15, 5, polygon)


def test_weighted_centroid_localization_maps_zone() -> None:
    readings = [
        {"gateway_id": "near", "rssi": -40},
        {"gateway_id": "far", "rssi": -70},
    ]
    gateways = {
        "near": {"x": 2.0, "y": 2.0},
        "far": {"x": 9.0, "y": 9.0},
        "zones": {"ward-a": [[0, 0], [5, 0], [5, 5], [0, 5]]},
    }

    result = weighted_centroid_localization(readings, gateways)

    assert result["x"] is not None and result["x"] < 5
    assert result["y"] is not None and result["y"] < 5
    assert result["zone_id"] == "ward-a"
    assert result["gateway_count"] == 2
    assert result["method"] == "wcl_zone_level"


def test_weighted_centroid_returns_insufficient_for_one_reading() -> None:
    result = weighted_centroid_localization(
        [{"gateway_id": "gw-1", "rssi": -59}],
        {"gw-1": {"x": 1, "y": 2}},
    )
    assert result["ble_quality"] == 0.0
    assert result["x"] is None
    assert result["y"] is None
    assert result["zone_id"] is None
    assert result["gateway_count"] == 1
    assert result["rssi_spread"] == 0
    assert result["calibration"]["note"] == "site-simulated"
    assert result["method"] == "insufficient_gateways"


def test_weighted_centroid_returns_insufficient_for_duplicate_gateway_readings() -> None:
    result = weighted_centroid_localization(
        [
            {"gateway_id": "gw-1", "rssi": -50},
            {"gateway_id": "gw-1", "rssi": -55},
        ],
        {"gw-1": {"x": 1, "y": 2}},
    )

    assert result["ble_quality"] == 0.0
    assert result["x"] is None
    assert result["y"] is None
    assert result["zone_id"] is None
    assert result["gateway_count"] == 1
    assert result["rssi_spread"] == 5


def test_compute_ble_quality_scores_count_spread_freshness_and_outliers() -> None:
    recent = datetime.now(UTC).isoformat()
    readings = [
        {"gateway_id": "gw-1", "rssi": -50, "timestamp": recent},
        {"gateway_id": "gw-2", "rssi": -52, "timestamp": recent},
        {"gateway_id": "gw-3", "rssi": -51, "timestamp": recent},
        {"gateway_id": "gw-4", "rssi": -90, "timestamp": recent},
    ]
    quality = compute_ble_quality(readings, {})
    assert quality == 0.94


def test_compute_ble_quality_uses_distinct_gateway_count() -> None:
    assert compute_ble_quality(
        [
            {"gateway_id": "gw-1", "rssi": -50},
            {"gateway_id": "gw-1", "rssi": -55},
        ],
        {},
    ) == 0.0


def test_compute_ble_quality_decays_stale_readings() -> None:
    stale = (datetime.now(UTC) - timedelta(seconds=300)).isoformat()
    readings = [
        {"gateway_id": "gw-1", "rssi": -50, "timestamp": stale},
        {"gateway_id": "gw-2", "rssi": -52, "timestamp": stale},
    ]
    assert compute_ble_quality(readings, {}) < compute_ble_quality(
        [
            {"gateway_id": "gw-1", "rssi": -50},
            {"gateway_id": "gw-2", "rssi": -52},
        ],
        {},
    )
