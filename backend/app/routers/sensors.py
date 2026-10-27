from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera, Gateway, SensorHeartbeat

router = APIRouter(tags=["sensors"])


class HeartbeatPayload(BaseModel):
    timestamp: datetime


@router.post("/sensors/{sensor_id}/heartbeat")
def receive_heartbeat(
    sensor_id: str,
    payload: HeartbeatPayload,
    db: Session = Depends(get_db),
) -> dict[str, str | datetime]:
    try:
        sensor_uuid = UUID(sensor_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Sensor not found") from error

    sensor = db.get(Camera, sensor_uuid)
    if sensor is None:
        sensor = db.get(Gateway, sensor_uuid)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")

    heartbeat_at = payload.timestamp
    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=UTC)

    age_seconds = (datetime.now(UTC) - heartbeat_at).total_seconds()
    timeout_seconds = sensor.heartbeat_timeout_s
    if age_seconds < timeout_seconds:
        sensor_status = "active"
    elif age_seconds < 2 * timeout_seconds:
        sensor_status = "degraded"
    else:
        sensor_status = "offline"

    sensor.last_heartbeat_at = heartbeat_at
    sensor.last_seen_at = heartbeat_at
    sensor.status = sensor_status
    db.add(
        SensorHeartbeat(
            sensor_type="camera" if isinstance(sensor, Camera) else "gateway",
            sensor_id=str(sensor.id),
            timestamp=heartbeat_at,
        )
    )
    db.commit()

    return {
        "status": sensor_status,
        "last_heartbeat_at": heartbeat_at,
    }
