from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset
from app.services.status_sweep import run_status_expiry_sweep

router = APIRouter(tags=["admin"])


class StatusSweepRequest(BaseModel):
    asset_id: UUID | None = None


@router.post("/status-sweep")
def status_sweep(
    request: StatusSweepRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if request is not None and request.asset_id is not None:
        asset = db.get(Asset, request.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        if asset.operational_status == "status_unknown" or asset.status_stale_after is None:
            raise HTTPException(
                status_code=409,
                detail="Asset has no active confirmation window",
            )
        asset.status_stale_after = datetime.now(UTC) - timedelta(seconds=1)
        db.flush()

    expired_count = run_status_expiry_sweep(db)
    db.commit()
    return {"expired_count": expired_count}
