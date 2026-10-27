import pytest

from app.main import app
from app.services.forecast import build_forecast


def test_forecast_route_is_mounted() -> None:
    assert "/api/v1/forecast" in app.openapi()["paths"]


@pytest.mark.parametrize(
    ("demand", "usable", "expected_indicator", "expected_band"),
    [
        (10, 10, 0.0, "low"),
        (10, 8, 0.2, "low"),
        (10, 6, 0.4, "moderate"),
        (10, 5, 0.5, "high"),
        (4, 1, 0.75, "high"),
        (10, 3, 0.7, "high"),
        (10, 1, 0.9, "critical"),
        (5, 8, 0.0, "low"),
        (0, 0, 0.0, "low"),
    ],
)
def test_forecast_indicator_and_band(
    demand: int,
    usable: int,
    expected_indicator: float,
    expected_band: str,
) -> None:
    result = build_forecast(demand, usable)

    assert result["shortage_indicator"] == pytest.approx(expected_indicator)
    assert result["band"] == expected_band
    assert result["calibrated"] is False
    assert "not a probability" in result["reason"]


def test_forecast_reports_demand_usable_and_shortfall() -> None:
    result = build_forecast(demand=12, projected_usable=9)

    assert result["demand"] == 12
    assert result["projected_usable"] == 9
    assert result["shortage_indicator"] == pytest.approx(0.25)
    assert result["band"] == "moderate"
    assert "Demand 12" in result["reason"]
    assert "usable 9" in result["reason"]
    assert "shortfall 3" in result["reason"]
