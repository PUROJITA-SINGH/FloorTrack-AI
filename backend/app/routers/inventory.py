from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, Asset, AssetType, AuditLog, ParLevel, WebhookLog, Zone
from app.services.status_sweep import run_status_expiry_sweep

router = APIRouter(tags=["inventory"])

ACTIVE_PAR_ALERT_STATUSES = ("open", "acknowledged", "dismissed")

PROHIBITED_ALERT_TERMS = tuple(
    json.loads(
        Path(__file__).resolve().parents[1]
        .joinpath("prohibited_alert_terms.json")
        .read_text(encoding="utf-8")
    )
)
PROHIBITED_ALERT_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in PROHIBITED_ALERT_TERMS) + r")\b",
    re.IGNORECASE,
)
TITLE_PERSON_PATTERN = re.compile(
    r"\b(?:Dr\.?|Doctor|Nurse|Mr\.?|Mrs\.?|Ms\.?)\s+[A-Z][a-z]{1,30}\b"
)
PERSON_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]{1,30}\s+[A-Z][a-z]{1,30}\b")

BASE_ALLOWED_TITLE_CASE_PHRASES = {
    "infusion pump",
    "nurse station",
    "critical care",
    "emergency department",
    "ward alpha",
    "ward beta",
    "ward a",
    "ward b",
    "city hospital",
    "central supply",
    "operating room",
    "intensive care",
    "corridor 1",
    "storage room",
    "maintenance room",
    "par deficit",
    "location review",
    "surplus notice",
    "operational notice",
    "transfer recommendation",
}


COMMON_ALERT_WORDS = {
    "deficit", "surplus", "notice", "alert", "warning", "update", "report",
    "request", "record", "rebalance", "recommended", "transfer", "review",
    "required", "available", "storage", "inventory", "operational", "location",
    "care", "central", "supply", "room", "department", "unit", "floor",
    "ward", "station", "pump", "infusion", "critical", "equipment", "emergency",
    "operating", "general", "biomedical", "engineering", "maintenance",
    "patient", "status", "par", "needed", "level", "levels", "check"
}


def _get_allowed_phrases(db: Session | None = None) -> set[str]:
    phrases = set(BASE_ALLOWED_TITLE_CASE_PHRASES)
    if db is not None:
        try:
            for name in db.scalars(select(Zone.name)).all():
                phrases.add(name.casefold())
            for name in db.scalars(select(AssetType.name)).all():
                phrases.add(name.casefold())
        except Exception:
            pass
    return phrases


def validate_alert_text(title: str, message: str, db: Session | None = None) -> None:
    text = f"{title}. {message}"
    if PROHIBITED_ALERT_PATTERN.search(text):
        raise ValueError("Alert text contains a prohibited term")

    allowed = _get_allowed_phrases(db)

    # Check title prefixes: Dr. Rao, Nurse Priya, Mr. Smith, etc.
    for match in TITLE_PERSON_PATTERN.finditer(text):
        matched_str = match.group(0).casefold()
        if matched_str in allowed:
            continue
        words = matched_str.split()
        if len(words) == 2 and words[1] in COMMON_ALERT_WORDS:
            continue
        raise ValueError("Alert text must not contain an individual's name")

    # Check two Title-Case words (e.g. John Smith)
    for match in PERSON_NAME_PATTERN.finditer(text):
        matched_str = match.group(0).casefold()
        if matched_str in allowed:
            continue
        words = matched_str.split()
        if len(words) == 2 and (words[0] in COMMON_ALERT_WORDS or words[1] in COMMON_ALERT_WORDS):
            continue
        raise ValueError("Alert text must not contain an individual's name")


def _inventory_query(db: Session, now: datetime) -> list[Any]:
    usable_count = func.count(Asset.id).filter(
        and_(
            Asset.operational_status == "available",
            (Asset.status_stale_after > now) | (Asset.status_stale_after.is_(None)),
        )
    )
    in_use_count = func.count(Asset.id).filter(
        Asset.operational_status == "in_use",
        (Asset.status_stale_after > now) | Asset.status_stale_after.is_(None),
    )
    maintenance_count = func.count(Asset.id).filter(
        Asset.operational_status == "maintenance",
        (Asset.status_stale_after > now) | Asset.status_stale_after.is_(None),
    )
    status_unknown_count = func.count(Asset.id).filter(
        Asset.operational_status == "status_unknown"
    )
    return db.execute(
        select(
            Zone.id.label("zone_id"),
            Zone.name.label("zone_name"),
            AssetType.id.label("asset_type_id"),
            AssetType.name.label("asset_type_name"),
            usable_count.label("usable_count"),
            in_use_count.label("in_use_count"),
            maintenance_count.label("maintenance_count"),
            status_unknown_count.label("status_unknown_count"),
            ParLevel.par_count.label("par_count"),
        )
        .select_from(ParLevel)
        .join(Zone, Zone.id == ParLevel.zone_id)
        .join(AssetType, AssetType.id == ParLevel.asset_type_id)
        .outerjoin(
            Asset,
            and_(
                Asset.current_zone_id == ParLevel.zone_id,
                Asset.asset_type_id == ParLevel.asset_type_id,
            ),
        )
        .group_by(
            Zone.id,
            Zone.name,
            AssetType.id,
            AssetType.name,
            ParLevel.par_count,
        )
        .order_by(Zone.name, AssetType.name)
    ).all()


def ensure_par_deficit_alerts(db: Session) -> None:
    rows = _inventory_query(db, datetime.now(UTC))
    existing = db.execute(
        select(Alert.zone_id, Alert.asset_type_id, Alert.status).where(
            Alert.alert_type == "par_deficit",
        )
    ).all()
    alerts_by_pair: dict[tuple[Any, Any], list[str]] = {}
    for zone_id, asset_type_id, status in existing:
        alerts_by_pair.setdefault((zone_id, asset_type_id), []).append(status)
    created = False
    changed = False
    for row in rows:
        usable = row.usable_count or 0
        deficit = max(0, row.par_count - usable)
        key = (row.zone_id, row.asset_type_id)
        existing_statuses = alerts_by_pair.get(key, [])
        if deficit == 0:
            for alert in db.scalars(
                select(Alert).where(
                    Alert.zone_id == row.zone_id,
                    Alert.asset_type_id == row.asset_type_id,
                    Alert.alert_type == "par_deficit",
                    Alert.status.in_(ACTIVE_PAR_ALERT_STATUSES),
                )
            ):
                alert.status = "resolved"
                changed = True
            continue
        if any(status in {"open", "acknowledged", "dismissed"} for status in existing_statuses):
            continue

        generated_title = "PAR deficit"
        message = (
            f"Usable count ({usable}) is below PAR ({row.par_count}). "
            f"{deficit} additional units recommended."
        )
        validate_alert_text(generated_title, message, db)
        db.add(
            Alert(
                alert_type="par_deficit",
                zone_id=row.zone_id,
                asset_type_id=row.asset_type_id,
                count=usable,
                par_count=row.par_count,
                severity="high" if usable == 0 else "medium",
                title=generated_title,
                message=message,
                status="open",
            )
        )
        created = True
        alerts_by_pair.setdefault(key, []).append("open")

    if created or changed:
        db.commit()


@router.get("")
def get_inventory(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    expired = run_status_expiry_sweep(db)
    if expired:
        db.commit()
    ensure_par_deficit_alerts(db)
    now = datetime.now(UTC)
    rows = _inventory_query(db, now)
    inventory = []
    for row in rows:
        usable = row.usable_count or 0
        par = row.par_count
        deficit = max(0, par - usable)
        inventory.append(
            {
                "zone_name": row.zone_name,
                "asset_type_name": row.asset_type_name,
                "usable_count": usable,
                "available_count": usable,
                "in_use_count": row.in_use_count or 0,
                "maintenance_count": row.maintenance_count or 0,
                "status_unknown_count": row.status_unknown_count or 0,
                "par_count": par,
                "status": "ok" if usable >= par else "deficit",
                "deficit_count": deficit,
            }
        )

    return inventory


class RedistributionDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_zone_id: str = Field(min_length=1)
    destination_zone_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    created_by: str = Field(min_length=1)


class DraftConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1)


@router.get("/recommendations")
def redistribution_recommendations(
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    expired = run_status_expiry_sweep(db)
    if expired:
        db.commit()
    rows = _inventory_query(db, datetime.now(UTC))
    deficits = [row for row in rows if (row.usable_count or 0) < row.par_count]
    surpluses = sorted(
        (row for row in rows if (row.usable_count or 0) > row.par_count),
        key=lambda row: (-(row.usable_count - row.par_count), row.zone_name),
    )
    recommendations: list[dict[str, Any]] = []
    used_asset_ids: set[str] = set()
    remaining_surplus = {
        row.zone_id: max(0, (row.usable_count or 0) - row.par_count)
        for row in surpluses
    }
    for deficit in deficits:
        remaining = deficit.par_count - (deficit.usable_count or 0)
        for surplus in surpluses:
            if remaining_surplus[surplus.zone_id] <= 0:
                continue
            if surplus.asset_type_id != deficit.asset_type_id:
                continue
            source_assets = db.scalars(
                select(Asset)
                .where(
                    Asset.current_zone_id == surplus.zone_id,
                    Asset.asset_type_id == surplus.asset_type_id,
                    Asset.operational_status == "available",
                    (Asset.status_stale_after > datetime.now(UTC))
                    | Asset.status_stale_after.is_(None),
                )
                .order_by(Asset.code)
            ).all()
            candidate = next(
                (asset for asset in source_assets if str(asset.id) not in used_asset_ids),
                None,
            )
            if candidate is None:
                continue
            used_asset_ids.add(str(candidate.id))
            remaining_surplus[surplus.zone_id] -= 1
            recommendations.append(
                {
                    "source_zone": surplus.zone_name,
                    "destination_zone": deficit.zone_name,
                    "asset_id": str(candidate.id),
                    "asset_code": candidate.code,
                    "asset_type": deficit.asset_type_name,
                    "status": "draft",
                    "requires_human_confirmation": True,
                    "reason": "Usable supply exceeds the source PAR and the destination is below PAR.",
                }
            )
            remaining -= 1
            if remaining == 0:
                break
        if remaining == 0:
            continue
    return recommendations


@router.post("/redistributions")
def create_redistribution_draft(
    payload: RedistributionDraftPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from uuid import UUID

    actor = payload.created_by.strip()
    try:
        source_zone_id = UUID(payload.source_zone_id)
        destination_zone_id = UUID(payload.destination_zone_id)
        asset_id = UUID(payload.asset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Draft IDs must be valid UUIDs") from error
    if (
        db.get(Zone, source_zone_id) is None
        or db.get(Zone, destination_zone_id) is None
        or db.get(Asset, asset_id) is None
    ):
        raise HTTPException(status_code=404, detail="Draft source, destination, or asset not found")
    draft_payload = {
        "source_zone_id": str(source_zone_id),
        "destination_zone_id": str(destination_zone_id),
        "asset_id": str(asset_id),
        "created_by": actor,
    }
    draft = WebhookLog(
        webhook_type="redistribution",
        payload=draft_payload,
        status="draft",
    )
    db.add(draft)
    db.commit()
    return {
        "id": str(draft.id),
        "status": draft.status,
        "requires_human_confirmation": True,
    }


@router.post("/redistributions/{draft_id}/confirm")
def confirm_redistribution_draft(
    draft_id: str,
    payload: DraftConfirmation,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from uuid import UUID

    from fastapi import HTTPException

    try:
        draft_uuid = UUID(draft_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Draft not found") from error
    draft = db.get(WebhookLog, draft_uuid)
    actor = payload.actor.strip()
    if draft is None or draft.webhook_type != "redistribution":
        raise HTTPException(status_code=404, detail="Draft not found")
    if not actor:
        raise HTTPException(status_code=422, detail="actor is required")
    if draft.status != "draft":
        raise HTTPException(status_code=409, detail="Draft is no longer pending")
    draft.status = "confirmed"
    db.add(
        AuditLog(
            action="redistribution_confirmed",
            entity_type="redistribution_draft",
            entity_id=str(draft.id),
            actor=actor,
            details=draft.payload,
        )
    )
    db.commit()
    return {"id": str(draft.id), "status": draft.status, "confirmed_by": actor}
