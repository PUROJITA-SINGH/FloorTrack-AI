from datetime import UTC, datetime
import math
from statistics import median
from typing import TypedDict
from collections.abc import Mapping, Sequence
from typing import Any

TX_POWER = -59.0
PATH_LOSS_EXPONENT = 2.0
FRESHNESS_GRACE_SECONDS = 60.0
FRESHNESS_EXPIRY_SECONDS = 300.0


class CalibrationInfo(TypedDict):
    tx_power: float
    path_loss_exponent: float
    note: str
    gateway_coordinates: dict[str, dict[str, float]]


class LocalizationResult(TypedDict):
    x: float | None
    y: float | None
    zone_id: str | None
    gateway_count: int
    ble_quality: float
    rssi_spread: float
    calibration: CalibrationInfo
    method: str


def rssi_to_distance(
    rssi: float,
    tx_power: float = TX_POWER,
    path_loss_exponent: float = PATH_LOSS_EXPONENT,
) -> float:
    """Convert RSSI to distance using the simulated log-distance path-loss model.

    Constants are site-simulated until walk-test calibration exists.
    """
    return 10 ** ((tx_power - rssi) / (10 * path_loss_exponent))


def get_calibration_info(
    gateways: Mapping[str, Any] | None = None,
) -> CalibrationInfo:
    return {
        "tx_power": TX_POWER,
        "path_loss_exponent": PATH_LOSS_EXPONENT,
        "note": "site-simulated",
        "gateway_coordinates": {
            str(gateway_id): {
                "x": float(gateway["x"]),
                "y": float(gateway["y"]),
            }
            for gateway_id, gateway in (gateways or {}).items()
            if gateway_id != "zones"
        },
    }


def point_in_polygon(
    x: float,
    y: float,
    polygon: Sequence[Sequence[float]],
) -> bool:
    """Return whether a point falls inside a polygon using ray casting."""
    if len(polygon) < 3:
        return False

    inside = False
    previous_x, previous_y = polygon[-1]
    for current_x, current_y in polygon:
        crosses_y = (current_y > y) != (previous_y > y)
        if crosses_y:
            intersection_x = (
                (previous_x - current_x) * (y - current_y)
                / (previous_y - current_y)
                + current_x
            )
            if x < intersection_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y

    return inside


def _reading_timestamps(readings: Sequence[Mapping[str, Any]]) -> list[datetime]:
    timestamps: list[datetime] = []
    for reading in readings:
        value = reading.get("timestamp")
        if value is None:
            continue
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime):
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        timestamps.append(value.astimezone(UTC))
    return timestamps


def compute_ble_quality(
    readings: list[dict[str, Any]],
    gateways: dict[str, Any],
) -> float:
    distinct_gateway_count = len(
        {str(reading["gateway_id"]) for reading in readings}
    )
    if distinct_gateway_count < 2:
        return 0.0

    gateway_count_score = min(distinct_gateway_count / 4.0, 1.0)

    rssi_values = [float(reading["rssi"]) for reading in readings]
    rssi_spread_score = 1.0 if max(rssi_values) != min(rssi_values) else 0.5

    timestamps = _reading_timestamps(readings)
    if timestamps:
        now = datetime.now(UTC)
        scores = []
        for timestamp in timestamps:
            age_seconds = max(0.0, (now - timestamp).total_seconds())
            if age_seconds <= FRESHNESS_GRACE_SECONDS:
                scores.append(1.0)
            else:
                remaining = FRESHNESS_EXPIRY_SECONDS - age_seconds
                decay_window = FRESHNESS_EXPIRY_SECONDS - FRESHNESS_GRACE_SECONDS
                scores.append(max(0.0, remaining / decay_window))
        freshness_score = sum(scores) / len(scores)
    else:
        freshness_score = 1.0

    rssi_median = median(rssi_values)
    consistent_count = sum(abs(value - rssi_median) <= 15.0 for value in rssi_values)
    consistency_score = consistent_count / len(rssi_values)

    return round(
        (
            gateway_count_score
            + rssi_spread_score
            + freshness_score
            + consistency_score
        )
        / 4.0,
        2,
    )


def weighted_centroid_localization(
    readings: list[dict[str, Any]],
    gateways: dict[str, Any],
) -> LocalizationResult:
    """Estimate location from RSSI-weighted gateway positions.

    Optionally provide zone polygons as ``gateways["zones"]``, a mapping from
    zone IDs to polygon coordinate arrays. Readings with no timestamp are
    treated as fresh; timestamped readings begin decaying after 60 seconds and
    reach zero freshness after 300 seconds.
    """
    valid_readings = [
        reading
        for reading in readings
        if str(reading.get("gateway_id")) in gateways
        and isinstance(reading.get("rssi"), (int, float))
        and math.isfinite(float(reading["rssi"]))
        and -127.0 <= float(reading["rssi"]) <= 0.0
    ]
    distinct_gateway_count = len(
        {str(reading["gateway_id"]) for reading in valid_readings}
    )
    rssi_values = [float(reading["rssi"]) for reading in valid_readings]
    rssi_spread = max(rssi_values) - min(rssi_values) if rssi_values else 0.0
    calibration = get_calibration_info(gateways)
    if distinct_gateway_count < 2:
        return {
            "ble_quality": 0.0,
            "rssi_spread": rssi_spread,
            "calibration": calibration,
            "x": None,
            "y": None,
            "zone_id": None,
            "gateway_count": distinct_gateway_count,
            "method": "insufficient_gateways",
        }

    weighted_x = 0.0
    weighted_y = 0.0
    weight_total = 0.0
    for reading in valid_readings:
        gateway = gateways.get(str(reading["gateway_id"]))
        if gateway is None:
            continue
        distance = rssi_to_distance(float(reading["rssi"]))
        weight = 1.0 / (distance**2)
        weighted_x += weight * float(gateway["x"])
        weighted_y += weight * float(gateway["y"])
        weight_total += weight

    if weight_total == 0:
        return {
            "ble_quality": compute_ble_quality(valid_readings, gateways),
            "rssi_spread": rssi_spread,
            "calibration": calibration,
            "x": None,
            "y": None,
            "zone_id": None,
            "gateway_count": distinct_gateway_count,
            "method": "insufficient_gateways",
        }

    x = weighted_x / weight_total
    y = weighted_y / weight_total
    zone_id: str | None = None
    zone_polygons = gateways.get("zones", {})
    if isinstance(zone_polygons, Mapping):
        for candidate_zone_id, polygon in zone_polygons.items():
            if point_in_polygon(x, y, polygon):
                zone_id = str(candidate_zone_id)
                break

    return {
        "x": x,
        "y": y,
        "zone_id": zone_id,
        "gateway_count": distinct_gateway_count,
        "ble_quality": compute_ble_quality(valid_readings, gateways),
        "rssi_spread": rssi_spread,
        "calibration": calibration,
        "method": "wcl_zone_level",
    }
