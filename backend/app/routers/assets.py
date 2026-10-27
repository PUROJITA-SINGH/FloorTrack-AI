from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import CONFIRMATION_WINDOW
from app.database import get_db
from app.models import (
    Asset,
    AssetCurrentState,
    AssetStatusHistory,
    AssetType,
    Camera,
    CoverageFigure,
    FusionDecision,
    LocationEstimate,
    MovementHistory,
    Tag,
    Zone,
)
from app.services.status_sweep import run_status_expiry_sweep

router = APIRouter(tags=["assets"])


class OperationalStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "available",
        "in_use",
        "maintenance",
        "status_unknown",
    ]
    source: str = Field(min_length=1)
    actor: str | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, min_length=1)
    adapter_name: str | None = None


@router.get("")
def list_assets(
    search: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    if run_status_expiry_sweep(db):
        db.commit()
    statement = select(Asset, AssetType.name).join(
        AssetType, AssetType.id == Asset.asset_type_id
    )
    if search:
        search_pattern = f"%{search}%"
        statement = statement.where(
            or_(
                Asset.code.ilike(search_pattern),
                Asset.serial_number.ilike(search_pattern),
                Asset.qr_code.ilike(search_pattern),
                select(Tag.id)
                .where(Tag.asset_id == Asset.id, Tag.tag_value.ilike(search_pattern))
                .exists(),
            )
        )
    if asset_type:
        statement = statement.where(
            or_(
                AssetType.name.ilike(asset_type),
                Asset.asset_type_id == _parse_uuid_or_none(asset_type),
            )
        )

    return [
        _asset_summary(db, asset, type_name)
        for asset, type_name in db.execute(statement.order_by(Asset.code)).all()
    ]


@router.get("/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if run_status_expiry_sweep(db):
        db.commit()
    asset = _get_asset_or_404(asset_id, db)
    asset_type = db.get(AssetType, asset.asset_type_id)
    return _asset_summary(db, asset, asset_type.name if asset_type else None)


@router.get("/{asset_id}/history")
def get_asset_history(
    asset_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    asset = _get_asset_or_404(asset_id, db)
    movements = db.scalars(
        select(MovementHistory)
        .where(MovementHistory.asset_id == asset.id)
        .order_by(MovementHistory.created_at.desc())
    ).all()
    history: list[dict[str, Any]] = []
    for movement in movements:
        decision = db.get(FusionDecision, movement.fusion_decision_id)
        from_zone = db.get(Zone, movement.from_zone_id) if movement.from_zone_id else None
        to_zone = db.get(Zone, movement.to_zone_id) if movement.to_zone_id else None
        history.append(
            {
                "timestamp": movement.created_at,
                "from_zone": from_zone.name if from_zone else None,
                "to_zone": to_zone.name if to_zone else None,
                "confidence_band": decision.confidence_band if decision else None,
                "decision_status": decision.decision_status if decision else None,
                "reason": decision.reason if decision else None,
                "evidence_links": decision.evidence_links if decision else [],
            }
        )
    return history


@router.get("/{asset_id}/status-history")
def get_asset_status_history(
    asset_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    asset = _get_asset_or_404(asset_id, db)
    history = db.scalars(
        select(AssetStatusHistory)
        .where(AssetStatusHistory.asset_id == asset.id)
        .order_by(AssetStatusHistory.created_at.desc())
    ).all()
    return [
        {
            "id": str(entry.id),
            "asset_id": str(entry.asset_id),
            "status": entry.status,
            "source": entry.source,
            "actor": entry.actor,
            "reason": entry.reason,
            "adapter_name": entry.adapter_name,
            "created_at": entry.created_at,
        }
        for entry in history
    ]


@router.post("/{asset_id}/operational-status")
def update_operational_status(
    asset_id: str,
    update: OperationalStatusUpdate,
    db: Session = Depends(get_db),
) -> dict[str, str | datetime]:
    if update.source not in {"user", "workflow_adapter"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid source: must be 'user' or 'workflow_adapter'",
        )

    if not update.reason or not update.reason.strip():
        raise HTTPException(status_code=400, detail="reason is required")

    if update.source == "user":
        if not update.actor or not update.actor.strip():
            raise HTTPException(status_code=400, detail="actor is required for user updates")
        actor = update.actor.strip()
        adapter_name = update.adapter_name or "user"
    else:
        if not update.adapter_name or not update.adapter_name.strip():
            raise HTTPException(
                status_code=400,
                detail="adapter_name is required for workflow_adapter updates",
            )
        actor = update.adapter_name.strip()
        adapter_name = update.adapter_name.strip()

    asset = _get_asset_or_404(asset_id, db)
    confirmed_at = datetime.now(UTC)
    stale_after = confirmed_at + CONFIRMATION_WINDOW

    try:
        asset.operational_status = update.status
        asset.status_source = update.source
        asset.status_actor = actor
        asset.status_reason = update.reason
        asset.status_confirmed_at = confirmed_at
        asset.status_stale_after = stale_after
        db.add(
            AssetStatusHistory(
                asset_id=asset.id,
                status=update.status,
                source=update.source,
                actor=actor,
                reason=update.reason,
                adapter_name=adapter_name,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "status": update.status,
        "source": update.source,
        "confirmed_at": confirmed_at,
        "stale_after": stale_after,
    }


def _parse_uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _get_asset_or_404(asset_id: str, db: Session) -> Asset:
    try:
        asset_uuid = UUID(asset_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Asset not found") from error
    asset = db.get(Asset, asset_uuid)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


def _asset_summary(
    db: Session,
    asset: Asset,
    asset_type_name: str | None,
) -> dict[str, Any]:
    current_state = db.scalar(
        select(AssetCurrentState).where(AssetCurrentState.asset_id == asset.id)
    )
    state_zone_id = asset.current_zone_id
    zone = db.get(Zone, state_zone_id) if state_zone_id else None
    camera_coverage = None
    camera_last_seen = None
    if zone is not None:
        covering_cameras = [
            camera
            for camera in db.scalars(
                select(Camera).where(Camera.floor_id == asset.floor_id)
            ).all()
            if isinstance(camera.coverage_zone_ids, list)
            and str(zone.id) in camera.coverage_zone_ids
        ]
        camera_last_seen = max(
            (
                camera.last_seen_at
                for camera in covering_cameras
                if camera.last_seen_at is not None
            ),
            default=None,
        )
        latest_coverage_at = db.scalar(
            select(func.max(CoverageFigure.computed_at)).where(
                CoverageFigure.zone_id == zone.id
            )
        )
        if latest_coverage_at is not None:
            camera_coverage = db.scalar(
                select(func.avg(CoverageFigure.coverage_percent)).where(
                    CoverageFigure.zone_id == zone.id,
                    CoverageFigure.computed_at == latest_coverage_at,
                )
            )
            if camera_coverage is not None:
                camera_coverage = float(camera_coverage)
    fusion_decision = None
    if current_state is not None and current_state.last_fusion_decision_id is not None:
        fusion_decision = db.get(FusionDecision, current_state.last_fusion_decision_id)
    if fusion_decision is None:
        fusion_decision = db.scalar(
            select(FusionDecision)
            .where(FusionDecision.asset_id == asset.id)
            .order_by(FusionDecision.created_at.desc())
            .limit(1)
        )
    location_estimate = db.scalar(
        select(LocationEstimate)
        .where(LocationEstimate.asset_id == asset.id)
        .order_by(LocationEstimate.created_at.desc())
        .limit(1)
    )
    camera_zone = (
        db.get(Zone, fusion_decision.camera_zone_id)
        if fusion_decision is not None and fusion_decision.camera_zone_id is not None
        else None
    )
    ble_zone = (
        db.get(Zone, fusion_decision.ble_zone_id)
        if fusion_decision is not None and fusion_decision.ble_zone_id is not None
        else None
    )
    confidence_breakdown = (
        fusion_decision.confidence_breakdown if fusion_decision is not None else None
    )
    fusion_detail = {
        "camera_zone": camera_zone.name if camera_zone is not None else None,
        "ble_zone": ble_zone.name if ble_zone is not None else None,
        "gateway_count": (
            location_estimate.gateway_count
            if location_estimate is not None
            else None
        ),
        "ble_quality": (
            location_estimate.ble_quality
            if location_estimate is not None
            else (
                confidence_breakdown.get("ble_quality")
                if isinstance(confidence_breakdown, dict)
                else None
            )
        ),
        "reason": fusion_decision.reason if fusion_decision is not None else None,
        "confidence_breakdown": confidence_breakdown,
        "evidence_links": (
            fusion_decision.evidence_links if fusion_decision is not None else []
        ),
        "rssi_spread": (
            confidence_breakdown.get("rssi_spread")
            if isinstance(confidence_breakdown, dict)
            else None
        ),
        "calibration": (
            fusion_decision.calibration_info if fusion_decision is not None else None
        ),
    }
    if fusion_detail["gateway_count"] is None and isinstance(confidence_breakdown, dict):
        fusion_detail["gateway_count"] = confidence_breakdown.get("gateway_count")
    last_fusion_at = asset.last_fusion_at
    if last_fusion_at is not None and last_fusion_at.tzinfo is None:
        last_fusion_at = last_fusion_at.replace(tzinfo=UTC)
    freshness = (
        max(0.0, (datetime.now(UTC) - last_fusion_at).total_seconds())
        if last_fusion_at is not None
        else None
    )
    return {
        "id": str(asset.id),
        "code": asset.code,
        "serial_number": asset.serial_number,
        "qr_code": asset.qr_code,
        "asset_type": asset_type_name,
        "asset_type_name": asset_type_name,
        "asset_type_id": str(asset.asset_type_id),
        "floor_id": str(asset.floor_id),
        "zone": zone.name if zone else None,
        "zone_id": str(asset.current_zone_id) if asset.current_zone_id else None,
        "current_zone_id": str(asset.current_zone_id) if asset.current_zone_id else None,
        "confidence_band": (
            current_state.confidence_band
            if current_state is not None
            else fusion_decision.confidence_band
            if fusion_decision is not None
            else None
        ),
        "decision_status": (
            current_state.decision_status
            if current_state is not None
            else fusion_decision.decision_status
            if fusion_decision is not None
            else None
        ),
        "confidence_breakdown": confidence_breakdown,
        "camera_zone_id": (
            str(fusion_decision.camera_zone_id)
            if fusion_decision is not None and fusion_decision.camera_zone_id
            else None
        ),
        "ble_zone_id": (
            str(fusion_decision.ble_zone_id)
            if fusion_decision is not None and fusion_decision.ble_zone_id
            else None
        ),
        "camera_zone": camera_zone.name if camera_zone is not None else None,
        "ble_zone": ble_zone.name if ble_zone is not None else None,
        "decision_reason": fusion_decision.reason if fusion_decision is not None else None,
        "disagreement_reason": (
            fusion_decision.reason
            if fusion_decision is not None
            and (
                (
                    current_state is not None
                    and current_state.decision_status == "sensor_disagreement"
                )
                or fusion_decision.decision_status == "sensor_disagreement"
            )
            else None
        ),
        "camera_coverage": camera_coverage,
        "camera_last_seen": camera_last_seen,
        "fusion_detail": fusion_detail,
        "freshness": freshness,
        "operational_status": asset.operational_status,
        "status_source": asset.status_source,
        "status_actor": (
            asset.status_actor
            if asset.operational_status != "status_unknown" and asset.status_confirmed_at is not None
            else None
        ),
        "status_reason": asset.status_reason,
        "status_confirmed_at": asset.status_confirmed_at,
        "status_stale_after": asset.status_stale_after,
        "last_fusion_at": asset.last_fusion_at,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }
