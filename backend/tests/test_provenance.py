from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Asset, AssetType, Facility, Floor


@pytest.fixture
def status_test_context() -> Iterator[tuple[Session, Floor, AssetType]]:
    with SessionLocal() as session:
        facility = Facility(name="Status provenance test")
        session.add(facility)
        session.flush()
        floor = Floor(facility_id=facility.id, name="Floor 1", floor_number=1)
        asset_type = AssetType(name="Infusion Pump")
        session.add_all([floor, asset_type])
        session.flush()
        yield session, floor, asset_type
        session.rollback()


def make_asset(
    floor: Floor,
    asset_type: AssetType,
    *,
    source: str = "workflow_adapter",
    actor: str = "test-fixture",
    reason: str = "test setup",
    status: str = "status_unknown",
    stale_after: datetime | None = None,
) -> Asset:
    return Asset(
        code="STATUS-TEST",
        asset_type_id=asset_type.id,
        floor_id=floor.id,
        operational_status=status,
        status_source=source,
        status_actor=actor,
        status_reason=reason,
        status_stale_after=stale_after,
    )


@pytest.mark.parametrize("source", ["bulk_import", "sensor"])
def test_database_rejects_untrusted_status_sources(
    status_test_context: tuple[Session, Floor, AssetType],
    source: str,
) -> None:
    session, floor, asset_type = status_test_context
    session.add(make_asset(floor, asset_type, source=source))
    with pytest.raises(IntegrityError, match="Invalid operational status provenance"):
        session.commit()
    session.rollback()


def test_user_status_with_provenance_is_accepted(
    status_test_context: tuple[Session, Floor, AssetType],
) -> None:
    session, floor, asset_type = status_test_context
    asset = make_asset(
        floor,
        asset_type,
        source="user",
        actor="unit manager",
        reason="confirmed ready for use",
        status="available",
        stale_after=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(asset)
    session.commit()
    assert asset.id is not None


def test_status_change_requires_new_provenance(
    status_test_context: tuple[Session, Floor, AssetType],
) -> None:
    session, floor, asset_type = status_test_context
    asset = make_asset(floor, asset_type)
    session.add(asset)
    session.commit()
    asset.operational_status = "maintenance"
    with pytest.raises(
        IntegrityError,
        match="Operational status changes require valid provenance",
    ):
        session.commit()
    session.rollback()


def test_available_status_requires_expiry(
    status_test_context: tuple[Session, Floor, AssetType],
) -> None:
    session, floor, asset_type = status_test_context
    session.add(
        make_asset(
            floor,
            asset_type,
            source="user",
            actor="unit manager",
            reason="confirmed",
            status="available",
        )
    )
    with pytest.raises(IntegrityError, match="Invalid operational status provenance"):
        session.commit()
    session.rollback()
