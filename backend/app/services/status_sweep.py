from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, AssetStatusHistory


def run_status_expiry_sweep(session: Session) -> int:
    now = datetime.now(UTC)
    expired_assets = session.scalars(
        select(Asset).where(
            Asset.status_stale_after.is_not(None),
            Asset.status_stale_after < now,
            Asset.operational_status != "status_unknown",
        )
    ).all()
    for asset in expired_assets:
        asset.operational_status = "status_unknown"
        asset.status_stale_after = None
        asset.status_source = "workflow_adapter"
        asset.status_actor = "status-expiry-sweep"
        asset.status_reason = "confirmation window elapsed"
        asset.status_confirmed_at = now
        session.add(
            AssetStatusHistory(
                asset_id=asset.id,
                status="status_unknown",
                source="workflow_adapter",
                actor="status-expiry-sweep",
                reason="confirmation window elapsed",
                adapter_name="status-expiry-sweep",
            )
        )
    session.flush()
    return len(expired_assets)
