from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Asset, Tag

if TYPE_CHECKING:
    from app.routers.events import CameraDetection

def resolve_asset(
    identifier: str,
    id_type: str,
    session: Session | None = None,
) -> Asset | None:
    owns_session = session is None
    db = session if session is not None else SessionLocal()
    try:
        if id_type == "tag":
            statement = select(Asset).join(Tag, Tag.asset_id == Asset.id).where(
                Tag.tag_value == identifier
            )
        elif id_type == "serial":
            statement = select(Asset).where(Asset.serial_number == identifier)
        elif id_type == "qr":
            statement = select(Asset).where(Asset.qr_code == identifier)
        else:
            raise ValueError(f"Unsupported asset identifier type: {id_type}")
        return db.scalar(statement.limit(1))
    finally:
        if owns_session:
            db.close()


def resolve_from_camera(
    detection: CameraDetection,
    session: Session | None = None,
) -> Asset | None:
    serial_number = getattr(detection, "serial_number", None)
    if serial_number:
        asset = resolve_asset(serial_number, "serial", session)
        if asset is not None:
            return asset

    qr_code = getattr(detection, "qr_code", None)
    if qr_code:
        asset = resolve_asset(qr_code, "qr", session)
        if asset is not None:
            return asset

    identifier = detection.asset_identifier
    return (
        resolve_asset(identifier, "tag", session)
        or resolve_asset(identifier, "serial", session)
        or resolve_asset(identifier, "qr", session)
    )


def resolve_from_ble(tag_id: str, session: Session | None = None) -> Asset | None:
    return resolve_asset(tag_id, "tag", session)
