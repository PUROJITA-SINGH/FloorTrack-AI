from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Asset, AssetStatusHistory, AssetType, Facility, Floor
from app.services.status_sweep import run_status_expiry_sweep


def test_status_expiry_sweep_updates_expired_assets_once() -> None:
    with SessionLocal() as session:
        facility = Facility(name="Sweep test facility")
        session.add(facility)
        session.flush()
        floor = Floor(
            facility_id=facility.id,
            name="Sweep test floor",
            floor_number=1,
        )
        asset_type = AssetType(name="Sweep test asset")
        session.add_all([floor, asset_type])
        session.flush()
        asset = Asset(
            code="SWEEP-TEST",
            asset_type_id=asset_type.id,
            floor_id=floor.id,
            operational_status="available",
            status_source="user",
            status_actor="unit manager",
            status_reason="confirmed",
            status_stale_after=datetime.now(UTC) - timedelta(minutes=1),
        )
        session.add(asset)
        session.commit()

        assert run_status_expiry_sweep(session) == 1
        session.commit()
        assert run_status_expiry_sweep(session) == 0

        session.refresh(asset)
        assert asset.operational_status == "status_unknown"
        assert asset.status_stale_after is None
        assert asset.status_source == "workflow_adapter"
        assert asset.status_actor == "status-expiry-sweep"
        assert asset.status_reason == "confirmation window elapsed"
        history = session.scalars(
            select(AssetStatusHistory).where(
                AssetStatusHistory.asset_id == asset.id,
                AssetStatusHistory.status == "status_unknown",
            )
        ).all()
        assert len(history) == 1
