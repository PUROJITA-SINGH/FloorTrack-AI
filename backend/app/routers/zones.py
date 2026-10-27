from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Floor, Zone

router = APIRouter(tags=["zones"])


@router.get("/zones")
def list_zones(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    default_floor = db.scalar(select(Floor).where(Floor.floor_number == 1).order_by(Floor.created_at))
    if default_floor is None:
        default_floor = db.scalar(select(Floor).order_by(Floor.created_at))
    if default_floor is None:
        raise HTTPException(status_code=404, detail="No floor configured")

    return [
        {
            "id": str(zone.id),
            "name": zone.name,
            "zone_type": zone.zone_type,
            "polygon_json": zone.polygon_json,
            "floor_id": str(zone.floor_id),
        }
        for zone in db.scalars(select(Zone).where(Zone.floor_id == default_floor.id).order_by(Zone.name)).all()
    ]
