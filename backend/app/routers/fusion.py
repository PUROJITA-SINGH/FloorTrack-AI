from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset
from app.services.fusion import run_fusion

router = APIRouter(tags=["fusion"])


@router.post("/fusion/run")
def run_fusion_for_all_assets(
    asset_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if asset_id is None:
        asset_ids = db.scalars(select(Asset.id).order_by(Asset.code)).all()
    else:
        try:
            asset_uuid = UUID(asset_id)
        except ValueError:
            asset_uuid = None

        statement = select(Asset).where(Asset.code == asset_id)
        if asset_uuid is not None:
            statement = select(Asset).where(
                or_(Asset.code == asset_id, Asset.id == asset_uuid)
            )
        asset = db.scalar(statement)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        asset_ids = [asset.id]

    results = []
    for selected_asset_id in asset_ids:
        result = run_fusion(str(selected_asset_id), db)
        fusion_summary = {
            "asset_id": str(selected_asset_id),
            "status": result["status"],
            "decision_status": result.get("decision_status"),
            "confidence_band": result.get("confidence_band"),
            "review_state": result.get("review_state"),
            "review_alert_id": result.get("review_alert_id"),
            "reason": result.get("reason"),
            "camera_zone_id": result.get("camera_zone_id"),
            "ble_zone_id": result.get("ble_zone_id"),
            "evidence_links": result.get("evidence_links", []),
            "gateway_count": result.get("gateway_count"),
            "rssi_spread": result.get("rssi_spread"),
            "calibration": result.get("calibration"),
        }
        if "zone_id" in result:
            fusion_summary["zone_id"] = result["zone_id"]
        if result["status"] == "camera_silent":
            camera_last_seen = result.get("camera_last_seen")
            fusion_summary.update(
                {
                    "state_changed": False,
                    "coverage": result["coverage"],
                    "camera_last_seen": (
                        camera_last_seen.isoformat()
                        if isinstance(camera_last_seen, datetime)
                        else None
                    ),
                }
            )
        results.append(fusion_summary)

    return {"processed": len(results), "results": results}
