from datetime import UTC, datetime
from typing import cast
from uuid import UUID
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.routers import fusion


class FakeScalars:
    def __init__(self, values: list[UUID]) -> None:
        self.values = values

    def all(self) -> list[UUID]:
        return self.values


class FakeSession:
    def __init__(self, asset_ids: list[UUID]) -> None:
        self.asset_ids = asset_ids

    def scalars(self, _statement: object) -> FakeScalars:
        return FakeScalars(self.asset_ids)

    def scalar(self, _statement: object) -> SimpleNamespace | None:
        if not self.asset_ids:
            return None
        return SimpleNamespace(id=self.asset_ids[0])


def test_batch_fusion_returns_empty_results_for_no_assets() -> None:
    response = fusion.run_fusion_for_all_assets(
        asset_id=None,
        db=cast(Session, FakeSession([])),
    )

    assert response == {"processed": 0, "results": []}


def test_batch_fusion_runs_each_asset(monkeypatch) -> None:
    asset_ids = [
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
    ]
    calls: list[str] = []

    def fake_run_fusion(asset_id: str, _db: object) -> dict[str, object]:
        calls.append(asset_id)
        return {
            "status": "fused",
            "decision_status": "confirmed",
            "confidence_band": "high",
        }

    monkeypatch.setattr(fusion, "run_fusion", fake_run_fusion)

    response = fusion.run_fusion_for_all_assets(
        asset_id=None,
        db=cast(Session, FakeSession(asset_ids)),
    )

    assert calls == [str(asset_id) for asset_id in asset_ids]
    assert response["processed"] == 2
    assert [
        {
            key: result[key]
            for key in (
                "asset_id",
                "status",
                "decision_status",
                "confidence_band",
            )
        }
        for result in response["results"]
    ] == [
        {
            "asset_id": str(asset_ids[0]),
            "status": "fused",
            "decision_status": "confirmed",
            "confidence_band": "high",
        },
        {
            "asset_id": str(asset_ids[1]),
            "status": "fused",
            "decision_status": "confirmed",
            "confidence_band": "high",
        },
    ]


def test_batch_fusion_accepts_asset_code(monkeypatch) -> None:
    asset_id = UUID("00000000-0000-0000-0000-000000000042")
    calls: list[str] = []

    def fake_run_fusion(selected_asset_id: str, _db: object) -> dict[str, str]:
        calls.append(selected_asset_id)
        return {
            "status": "fused",
            "decision_status": "confirmed",
            "confidence_band": "high",
            "zone_id": "zone-1",
        }

    monkeypatch.setattr(fusion, "run_fusion", fake_run_fusion)
    response = fusion.run_fusion_for_all_assets(
        asset_id="P-042",
        db=cast(Session, FakeSession([asset_id])),
    )

    assert calls == [str(asset_id)]
    assert response["processed"] == 1
    assert response["results"][0]["asset_id"] == str(asset_id)
    assert response["results"][0]["zone_id"] == "zone-1"


def test_batch_fusion_preserves_camera_silence_coverage(monkeypatch) -> None:
    asset_id = UUID("00000000-0000-0000-0000-000000000042")
    camera_last_seen = datetime(2026, 10, 17, 10, 30, tzinfo=UTC)

    def fake_run_fusion(_asset_id: str, _db: object) -> dict[str, object]:
        return {
            "status": "camera_silent",
            "state_changed": False,
            "coverage": 25.0,
            "camera_last_seen": camera_last_seen,
        }

    monkeypatch.setattr(fusion, "run_fusion", fake_run_fusion)
    response = fusion.run_fusion_for_all_assets(
        asset_id=None,
        db=cast(Session, FakeSession([asset_id])),
    )

    result = response["results"][0]
    assert result["asset_id"] == str(asset_id)
    assert result["status"] == "camera_silent"
    assert result["decision_status"] is None
    assert result["confidence_band"] is None
    assert result["state_changed"] is False
    assert result["coverage"] == 25.0
    assert result["camera_last_seen"] == camera_last_seen.isoformat()
    assert result["gateway_count"] is None
    assert result["rssi_spread"] is None
    assert result["calibration"] is None
