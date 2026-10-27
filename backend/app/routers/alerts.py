from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, AssetType, AuditLog, WebhookLog, Zone
from app.routers.inventory import (
    ensure_par_deficit_alerts,
    validate_alert_text,
)

router = APIRouter(tags=["alerts"])


class AlertAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1)


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_type: Literal["operational_notice", "par_deficit", "surplus"]
    zone_id: UUID
    asset_type_id: UUID
    count: int = Field(ge=0)
    par_count: int = Field(ge=0)
    severity: Literal["low", "medium", "high"]
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)


class AlertConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1)
    channel: Literal["slack", "teams"] = "slack"


@router.get("")
def list_alerts(
    status: str | None = Query(default="open"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    statement = (
        select(Alert, Zone.name, AssetType.name)
        .join(Zone, Zone.id == Alert.zone_id)
        .join(AssetType, AssetType.id == Alert.asset_type_id)
    )
    if status is not None:
        statement = statement.where(Alert.status == status)

    return [
        {
            "id": str(alert.id),
            "alert_type": alert.alert_type,
            "zone_id": str(alert.zone_id),
            "zone_name": zone_name,
            "asset_type_id": str(alert.asset_type_id),
            "asset_id": str(alert.asset_id) if alert.asset_id else None,
            "asset_type_name": asset_type_name,
            "count": alert.count,
            "par_count": alert.par_count,
            "severity": alert.severity,
            "title": alert.title,
            "message": alert.message,
            "status": alert.status,
            "created_at": alert.created_at,
            "acknowledged_at": alert.acknowledged_at,
            "acknowledged_by": alert.acknowledged_by,
        }
        for alert, zone_name, asset_type_name in db.execute(
            statement.order_by(Alert.created_at.desc())
        ).all()
    ]


@router.post("/reconcile")
def reconcile_alerts(db: Session = Depends(get_db)) -> dict[str, str]:
    ensure_par_deficit_alerts(db)
    return {"status": "reconciled"}


@router.post("")
def create_alert(
    payload: AlertCreate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if db.get(Zone, payload.zone_id) is None or db.get(AssetType, payload.asset_type_id) is None:
        raise HTTPException(status_code=404, detail="Zone or asset type not found")
    try:
        validate_alert_text(payload.title, payload.message, db)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    alert = Alert(**payload.model_dump(), status="open")
    db.add(alert)
    db.commit()
    return {
        "id": str(alert.id),
        "alert_type": alert.alert_type,
        "title": alert.title,
        "message": alert.message,
        "status": alert.status,
    }


@router.post("/{alert_id}/confirm")
def confirm_alert(
    alert_id: UUID,
    confirmation: AlertConfirmation,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == "confirmed":
        raise HTTPException(status_code=409, detail="Alert is already confirmed")
    try:
        validate_alert_text(alert.title, alert.message, db)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    actor = confirmation.actor.strip()
    if not actor:
        raise HTTPException(status_code=422, detail="actor is required")
    alert.status = "confirmed"
    alert.acknowledged_at = datetime.now(UTC)
    alert.acknowledged_by = actor
    db.add(
        WebhookLog(
            webhook_type=confirmation.channel,
            payload={
                "alert_id": str(alert.id),
                "title": alert.title,
                "message": alert.message,
                "confirmed_by": actor,
            },
            status="received",
        )
    )
    db.add(
        AuditLog(
            action="alert_confirmed",
            entity_type="alert",
            entity_id=str(alert.id),
            actor=actor,
            details={"channel": confirmation.channel},
        )
    )
    db.commit()
    return {
        "id": str(alert.id),
        "status": alert.status,
        "confirmed_by": actor,
        "channel": confirmation.channel,
        "dispatched_to_mock_webhook": True,
    }


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: UUID,
    acknowledgement: AlertAcknowledgement,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(UTC)
    alert.acknowledged_by = acknowledgement.actor
    db.commit()
    return {
        "id": str(alert.id),
        "status": alert.status,
        "acknowledged_at": alert.acknowledged_at,
        "acknowledged_by": alert.acknowledged_by,
    }


@router.post("/{alert_id}/dismiss")
def dismiss_alert(alert_id: UUID, db: Session = Depends(get_db)) -> dict[str, str]:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "dismissed"
    db.commit()
    return {"id": str(alert.id), "status": alert.status}
