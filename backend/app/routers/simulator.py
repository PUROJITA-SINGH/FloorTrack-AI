from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, AssetType, Camera, Gateway, Tag, Zone

router = APIRouter(tags=["simulator"])


@router.get("/topology")
def get_simulator_topology(db: Session = Depends(get_db)) -> dict[str, Any]:
    assets = db.execute(
        select(Asset, AssetType.name)
        .join(AssetType, AssetType.id == Asset.asset_type_id)
        .order_by(Asset.code)
    ).all()
    tags = db.execute(select(Tag.asset_id, Tag.tag_value)).all()
    tags_by_asset: dict[str, list[str]] = {}
    for asset_id, tag_value in tags:
        tags_by_asset.setdefault(str(asset_id), []).append(tag_value)

    return {
        "assets": [
            {
                "id": str(asset.id),
                "code": asset.code,
                "serial_number": asset.serial_number,
                "qr_code": asset.qr_code,
                "tags": tags_by_asset.get(str(asset.id), []),
                "operational_status": asset.operational_status,
                "status_stale_after": asset.status_stale_after,
            }
            for asset, _asset_type_name in assets
        ],
        "zones": [
            {
                "id": str(zone.id),
                "name": zone.name,
                "polygon_json": zone.polygon_json,
            }
            for zone in db.scalars(select(Zone).order_by(Zone.name)).all()
        ],
        "cameras": [
            {
                "id": str(camera.id),
                "name": camera.name,
                "heartbeat_timeout_s": camera.heartbeat_timeout_s,
            }
            for camera in db.scalars(select(Camera).order_by(Camera.name)).all()
        ],
        "gateways": [
            {
                "id": str(gateway.id),
                "name": gateway.name,
                "x": gateway.x,
                "y": gateway.y,
                "heartbeat_timeout_s": gateway.heartbeat_timeout_s,
            }
            for gateway in db.scalars(select(Gateway).order_by(Gateway.name)).all()
        ],
    }
