from datetime import UTC, date, datetime, timedelta
from typing import Literal, TypedDict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, DemandEvent
from app.services.status_sweep import run_status_expiry_sweep

ForecastBand = Literal["low", "moderate", "high", "critical"]


class ForecastResult(TypedDict):
    demand: int
    projected_usable: int
    usable_supply: int
    shortfall_units: int
    horizon_days: int
    shortage_indicator: float
    indicator: float
    calibrated: bool
    band: ForecastBand
    reason: str


def build_forecast(
    demand: int,
    projected_usable: int,
    *,
    horizon_days: int = 7,
) -> ForecastResult:
    if demand < 0 or projected_usable < 0:
        raise ValueError("Demand and usable supply must be zero or greater")
    if horizon_days < 1:
        raise ValueError("Forecast horizon must be at least one day")
    shortfall = max(0, demand - projected_usable)
    indicator = 0.0 if demand == 0 else min(1.0, max(0.0, shortfall / demand))

    if indicator < 0.25:
        band: ForecastBand = "low"
    elif indicator < 0.5:
        band = "moderate"
    elif indicator <= 0.75:
        band = "high"
    else:
        band = "critical"

    return {
        "demand": demand,
        "projected_usable": projected_usable,
        "usable_supply": projected_usable,
        "shortfall_units": shortfall,
        "horizon_days": horizon_days,
        "shortage_indicator": round(indicator, 4),
        "indicator": round(indicator, 4),
        "calibrated": False,
        "band": band,
        "reason": (
            f"Demand {demand}, usable {projected_usable}, shortfall "
            f"{shortfall} (not a probability)."
        ),
    }


def get_forecast(
    db: Session,
    *,
    horizon_days: int,
    zone_id: UUID | None = None,
    asset_type_id: UUID | None = None,
    demand_count: int | None = None,
) -> ForecastResult:
    expired = run_status_expiry_sweep(db)
    if expired:
        db.commit()
    now = datetime.now(UTC)
    today = now.date()
    first_day = today - timedelta(days=horizon_days - 1)

    demand_query = select(func.coalesce(func.sum(DemandEvent.demand_count), 0)).where(
        DemandEvent.event_date >= first_day,
        DemandEvent.event_date <= today,
    )
    usable_query = select(func.count(Asset.id)).where(
        Asset.operational_status == "available",
        (Asset.status_stale_after > now) | Asset.status_stale_after.is_(None),
    )
    if zone_id is not None:
        demand_query = demand_query.where(DemandEvent.zone_id == zone_id)
        usable_query = usable_query.where(Asset.current_zone_id == zone_id)
    if asset_type_id is not None:
        demand_query = demand_query.where(DemandEvent.asset_type_id == asset_type_id)
        usable_query = usable_query.where(Asset.asset_type_id == asset_type_id)

    if demand_count is not None:
        demand = demand_count
    else:
        demand = db.scalar(demand_query)
    projected_usable = db.scalar(usable_query)
    return build_forecast(
        int(demand or 0),
        int(projected_usable or 0),
        horizon_days=horizon_days,
    )
