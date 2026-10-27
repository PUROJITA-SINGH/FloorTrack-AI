from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, AuditLog, WebhookLog
from app.routers.inventory import validate_alert_text

router = APIRouter(tags=["integrations"])


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    alert_id: str | None = None


class WorkOrderDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    created_by: str = Field(min_length=1, max_length=120)


class WorkOrderConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=120)


@router.post("/webhooks/{channel}")
def receive_mock_webhook(
    channel: str,
    payload: WebhookPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if channel not in {"slack", "teams"}:
        raise HTTPException(status_code=404, detail="Unsupported mock webhook channel")
    try:
        validate_alert_text(payload.title, payload.message, db)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record = WebhookLog(
        webhook_type=channel,
        payload=payload.model_dump(),
        status="received",
    )
    db.add(record)
    db.commit()
    return {"id": str(record.id), "channel": channel, "status": "received"}


@router.post("/cmms/work-orders")
def create_work_order_draft(
    payload: WorkOrderDraftPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    asset = db.get(Asset, payload.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    draft = WebhookLog(
        webhook_type="cmms_work_order",
        payload={
            "asset_id": str(asset.id),
            "asset_code": asset.code,
            "reason": payload.reason.strip(),
            "created_by": payload.created_by.strip(),
        },
        status="draft",
    )
    db.add(draft)
    db.commit()
    return {
        "id": str(draft.id),
        "status": draft.status,
        "requires_human_confirmation": True,
        "dispatched": False,
        "payload": draft.payload,
    }


@router.post("/cmms/work-orders/{draft_id}/confirm")
def confirm_work_order_draft(
    draft_id: UUID,
    confirmation: WorkOrderConfirmation,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    draft = db.get(WebhookLog, draft_id)
    if draft is None or draft.webhook_type != "cmms_work_order":
        raise HTTPException(status_code=404, detail="Work-order draft not found")
    if draft.status != "draft":
        raise HTTPException(status_code=409, detail="Draft is no longer pending")
    actor = confirmation.actor.strip()
    if not actor:
        raise HTTPException(status_code=422, detail="actor is required")
    draft.status = "confirmed"
    db.add(
        AuditLog(
            action="work_order_confirmed",
            entity_type="work_order_draft",
            entity_id=str(draft.id),
            actor=actor,
            details=draft.payload,
        )
    )
    db.commit()
    return {"id": str(draft.id), "status": draft.status, "confirmed_by": actor}
