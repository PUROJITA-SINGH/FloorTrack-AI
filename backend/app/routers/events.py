from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import (
    AssetType,
    BleEvent,
    Camera,
    CameraEvent,
    DemandEvent,
    Gateway,
    Tag,
    Zone,
)
from app.services.identity import resolve_from_camera
from app.services.identity import resolve_from_ble
from app.services.fusion import run_fusion

router = APIRouter(tags=["events"])


class CameraDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_identifier: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    zone_id: str | None = None
    serial_number: str | None = None
    qr_code: str | None = None


class CameraEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: str
    event_id: str
    timestamp: datetime
    detections: list[CameraDetection] = Field(min_length=1)


class BleReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_id: UUID
    rssi: float = Field(ge=-127.0, le=0.0)
    timestamp: datetime | None = None
    phase: float | None = None
    aoa_degrees: float | None = Field(default=None, ge=-180.0, le=180.0)


class BleEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_id: str
    event_id: str
    timestamp: datetime
    readings: list[BleReading] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_batch(self) -> "BleEventPayload":
        gateway_ids = [reading.gateway_id for reading in self.readings]
        if len(gateway_ids) != len(set(gateway_ids)):
            raise ValueError("A BLE batch may contain only one reading per gateway")

        batch_timestamp = self.timestamp
        if batch_timestamp.tzinfo is None:
            batch_timestamp = batch_timestamp.replace(tzinfo=UTC)
        for reading in self.readings:
            if reading.timestamp is None:
                continue
            reading_timestamp = reading.timestamp
            if reading_timestamp.tzinfo is None:
                reading_timestamp = reading_timestamp.replace(tzinfo=UTC)
            if reading_timestamp != batch_timestamp:
                raise ValueError("All BLE readings must use the batch timestamp")
        return self


class CombinedIngestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_events: list[CameraEventPayload] = Field(default_factory=list)
    ble_events: list[BleEventPayload] = Field(default_factory=list)


class DemandEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: UUID
    asset_type_id: UUID
    demand_count: int = Field(ge=0)
    event_date: date


def _fusion_result(asset_id: UUID, db: Session) -> dict[str, Any]:
    result = run_fusion(str(asset_id), db)
    fusion_result = {
        "asset_id": str(asset_id),
        "decision_status": result.get("decision_status"),
        "confidence_band": result.get("confidence_band"),
        "zone_id": result.get("zone_id"),
        "reason": result.get("reason"),
        "review_state": result.get("review_state"),
        "review_alert_id": result.get("review_alert_id"),
        "camera_zone_id": result.get("camera_zone_id"),
        "ble_zone_id": result.get("ble_zone_id"),
        "evidence_links": result.get("evidence_links", []),
        "gateway_count": result.get("gateway_count"),
        "rssi_spread": result.get("rssi_spread"),
        "calibration": result.get("calibration"),
    }
    if result.get("status") == "camera_silent":
        camera_last_seen = result.get("camera_last_seen")
        fusion_result.update(
            {
                "status": "camera_silent",
                "state_changed": False,
                "coverage": result["coverage"],
                "camera_last_seen": (
                    camera_last_seen.isoformat()
                    if isinstance(camera_last_seen, datetime)
                    else None
                ),
            }
        )
    return fusion_result


def _run_fusion_in_background(asset_id: str) -> None:
    with SessionLocal() as db:
        run_fusion(asset_id, db)


@router.post("/events/ble", status_code=201)
def ingest_ble_event(
    payload: BleEventPayload,
    background_tasks: BackgroundTasks = None,
    trigger_fusion: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> JSONResponse:
    existing_event = db.scalar(
        select(BleEvent.id).where(BleEvent.event_id == payload.event_id)
    )
    if existing_event is not None:
        return JSONResponse(
            status_code=200,
            content={"status": "duplicate", "event_id": payload.event_id},
        )

    tag = db.scalar(select(Tag).where(Tag.tag_value == payload.tag_id).limit(1))
    asset = resolve_from_ble(payload.tag_id, db)
    timestamp_events = db.scalars(
        select(BleEvent).where(BleEvent.timestamp == payload.timestamp)
    ).all()
    if any(
        event.raw_payload.get("tag_id") == payload.tag_id
        for event in timestamp_events
    ):
        raise HTTPException(
            status_code=409,
            detail="A BLE batch already exists for this tag and timestamp",
        )

    for reading in payload.readings:
        gateway = db.get(Gateway, reading.gateway_id)
        if gateway is None:
            raise HTTPException(status_code=422, detail="Unknown gateway_id")
        if reading.phase is not None and "phase" not in gateway.capabilities:
            raise HTTPException(
                status_code=422,
                detail=f"Gateway {gateway.name} has not declared phase capability",
            )
        if reading.aoa_degrees is not None and "aoa" not in gateway.capabilities:
            raise HTTPException(
                status_code=422,
                detail=f"Gateway {gateway.name} has not declared AoA capability",
            )
    db.add(
        BleEvent(
            tag_id=tag.id if tag is not None else None,
            asset_id=asset.id if asset is not None else None,
            event_id=payload.event_id,
            timestamp=payload.timestamp,
            readings=[
                reading.model_dump(mode="json", exclude_none=True)
                for reading in payload.readings
            ],
            raw_payload=payload.model_dump(mode="json"),
            unknown_asset=asset is None,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_event = db.scalar(
            select(BleEvent.id).where(BleEvent.event_id == payload.event_id)
        )
        if existing_event is not None:
            return JSONResponse(
                status_code=200,
                content={"status": "duplicate", "event_id": payload.event_id},
            )
        raise
    content: dict[str, Any] = {
        "status": "accepted",
        "event_id": payload.event_id,
        "readings_count": len(payload.readings),
    }
    if asset is not None and trigger_fusion:
        content["fusion_results"] = [_fusion_result(asset.id, db)]
    elif asset is not None and background_tasks is not None:
        background_tasks.add_task(_run_fusion_in_background, str(asset.id))
    return JSONResponse(
        status_code=201,
        content=content,
    )


@router.post("/events/camera", status_code=201)
def ingest_camera_event(
    payload: CameraEventPayload,
    background_tasks: BackgroundTasks = None,
    trigger_fusion: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> JSONResponse:
    existing_event = db.scalar(
        select(CameraEvent.id).where(CameraEvent.event_id == payload.event_id)
    )
    if existing_event is not None:
        return JSONResponse(
            status_code=200,
            content={"status": "duplicate", "event_id": payload.event_id},
        )

    try:
        camera_uuid = UUID(payload.camera_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="camera_id must be a valid UUID") from error

    camera = db.get(Camera, camera_uuid)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    stored_detections: list[dict[str, Any]] = []
    resolved_asset_ids: list[UUID | None] = []
    unknown_assets = 0
    for detection in payload.detections:
        asset = resolve_from_camera(detection, db)

        try:
            zone_uuid = UUID(detection.zone_id) if detection.zone_id is not None else None
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid zone_id for detection {detection.asset_identifier}",
            ) from error

        if zone_uuid is not None and db.get(Zone, zone_uuid) is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown zone_id for detection {detection.asset_identifier}",
            )

        is_unknown_asset = asset is None
        unknown_assets += int(is_unknown_asset)
        resolved_asset_ids.append(asset.id if asset is not None else None)
        stored_detections.append(
            {
                **detection.model_dump(mode="json"),
                "asset_id": str(asset.id) if asset is not None else None,
                "unknown_asset": is_unknown_asset,
            }
        )

    event_timestamp = payload.timestamp
    if event_timestamp.tzinfo is None:
        event_timestamp = event_timestamp.replace(tzinfo=UTC)

    event = CameraEvent(
        camera_id=camera.id,
        asset_id=resolved_asset_ids[0] if len(resolved_asset_ids) == 1 else None,
        event_id=payload.event_id,
        timestamp=event_timestamp,
        zone_id=(
            UUID(payload.detections[0].zone_id)
            if len(payload.detections) == 1 and payload.detections[0].zone_id is not None
            else None
        ),
        confidence=payload.detections[0].confidence if len(payload.detections) == 1 else None,
        raw_payload={
            **payload.model_dump(mode="json"),
            "detections": stored_detections,
        },
        unknown_asset=unknown_assets > 0,
    )
    if camera.last_seen_at is None or event_timestamp > camera.last_seen_at:
        camera.last_seen_at = event_timestamp
    db.add(event)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_event = db.scalar(
            select(CameraEvent.id).where(CameraEvent.event_id == payload.event_id)
        )
        if existing_event is not None:
            return JSONResponse(
                status_code=200,
                content={"status": "duplicate", "event_id": payload.event_id},
            )
        raise

    content: dict[str, Any] = {
        "status": "accepted",
        "event_id": payload.event_id,
        "detections_count": len(payload.detections),
    }
    distinct_asset_ids = list(
        dict.fromkeys(
            asset_id for asset_id in resolved_asset_ids if asset_id is not None
        )
    )
    if trigger_fusion:
        content["fusion_results"] = [
            _fusion_result(asset_id, db) for asset_id in distinct_asset_ids
        ]
    elif background_tasks is not None:
        for asset_id in distinct_asset_ids:
            background_tasks.add_task(_run_fusion_in_background, str(asset_id))
    return JSONResponse(status_code=201, content=content)


@router.post("/events/ingest-and-fuse")
def ingest_and_fuse(
    payload: CombinedIngestPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    camera_accepted = 0
    ble_accepted = 0
    asset_ids: list[UUID] = []

    for camera_payload in payload.camera_events:
        response = ingest_camera_event(
            camera_payload,
            trigger_fusion=False,
            db=db,
        )
        camera_accepted += int(response.status_code == 201)
        stored_event = db.scalar(
            select(CameraEvent).where(CameraEvent.event_id == camera_payload.event_id)
        )
        if stored_event is not None:
            for detection in stored_event.raw_payload.get("detections", []):
                stored_asset_id = detection.get("asset_id")
                if stored_asset_id:
                    asset_ids.append(UUID(stored_asset_id))

    for ble_payload in payload.ble_events:
        response = ingest_ble_event(
            ble_payload,
            trigger_fusion=False,
            db=db,
        )
        ble_accepted += int(response.status_code == 201)
        stored_event = db.scalar(
            select(BleEvent).where(BleEvent.event_id == ble_payload.event_id)
        )
        if stored_event is not None and stored_event.asset_id is not None:
            asset_ids.append(stored_event.asset_id)

    fusion_results = [
        _fusion_result(asset_id, db) for asset_id in dict.fromkeys(asset_ids)
    ]
    return {
        "camera_accepted": camera_accepted,
        "ble_accepted": ble_accepted,
        "fusion_results": fusion_results,
    }


@router.post("/events/demand", status_code=201)
def ingest_demand_event(
    payload: DemandEventPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if db.get(Zone, payload.zone_id) is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    if db.get(AssetType, payload.asset_type_id) is None:
        raise HTTPException(status_code=404, detail="Asset type not found")
    event = DemandEvent(**payload.model_dump())
    db.add(event)
    db.commit()
    return {
        "status": "accepted",
        "zone_id": str(event.zone_id),
        "asset_type_id": str(event.asset_type_id),
        "demand_count": event.demand_count,
        "event_date": event.event_date.isoformat(),
    }


@router.get("/events/{event_id}")
def get_event_evidence(
    event_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ble_event = db.scalar(select(BleEvent).where(BleEvent.event_id == event_id))
    if ble_event is not None:
        return {
            "event_id": event_id,
            "source": "ble",
            "asset_id": str(ble_event.asset_id) if ble_event.asset_id else None,
            "timestamp": ble_event.timestamp,
            "readings": ble_event.readings,
            "unknown_asset": ble_event.unknown_asset,
        }
    camera_event = db.scalar(
        select(CameraEvent).where(CameraEvent.event_id == event_id)
    )
    if camera_event is not None:
        return {
            "event_id": event_id,
            "source": "camera",
            "asset_id": str(camera_event.asset_id) if camera_event.asset_id else None,
            "timestamp": camera_event.timestamp,
            "detections": camera_event.raw_payload.get("detections", []),
            "unknown_asset": camera_event.unknown_asset,
        }
    raise HTTPException(status_code=404, detail="Evidence event not found")
