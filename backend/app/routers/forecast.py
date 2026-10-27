from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.forecast import ForecastResult, get_forecast

router = APIRouter(tags=["forecast"])


@router.get("/forecast")
def forecast(
    zone_id: UUID | None = Query(default=None),
    asset_type_id: UUID | None = Query(default=None),
    horizon_days: int = Query(default=7, ge=1),
    demand_count: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
) -> ForecastResult:
    return get_forecast(
        db,
        zone_id=zone_id,
        asset_type_id=asset_type_id,
        horizon_days=horizon_days,
        demand_count=demand_count,
    )
