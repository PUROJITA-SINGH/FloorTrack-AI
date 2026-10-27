import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime as SQLDateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB as PostgreSQLJSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.database import Base

UUID = Uuid
JSONB = JSON().with_variant(PostgreSQLJSONB(), "postgresql")


class UTCDateTime(TypeDecorator[datetime]):
    impl = SQLDateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(
        self,
        value: datetime | None,
        _dialect,
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


DateTime = UTCDateTime


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Floor(Base):
    __tablename__ = "floors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)
    svg_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    floor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    zone_type: Mapped[str] = mapped_column(Text, nullable=False)
    polygon_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AssetType(Base):
    __tablename__ = "asset_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_code", "code"),
        Index("ix_assets_asset_type_id", "asset_type_id"),
        Index("ix_assets_current_zone_id", "current_zone_id"),
        CheckConstraint(
            "operational_status IN ('available', 'in_use', 'maintenance', 'status_unknown')",
            name="ck_assets_operational_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(Text)
    qr_code: Mapped[str | None] = mapped_column(Text)
    asset_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_types.id"), nullable=False)
    floor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id"), nullable=False)
    current_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    operational_status: Mapped[str] = mapped_column(Text, nullable=False)
    status_source: Mapped[str] = mapped_column(Text, nullable=False)
    status_actor: Mapped[str] = mapped_column(Text, nullable=False)
    status_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_stale_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fusion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    tag_type: Mapped[str] = mapped_column(Text, nullable=False)
    tag_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Gateway(Base):
    __tablename__ = "gateways"
    __table_args__ = (Index("ix_gateways_last_heartbeat_at", "last_heartbeat_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    floor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(Double, nullable=False)
    y: Mapped[float] = mapped_column(Double, nullable=False)
    heartbeat_timeout_s: Mapped[int] = mapped_column(Integer, nullable=False)
    capabilities: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (Index("ix_cameras_last_heartbeat_at", "last_heartbeat_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    floor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_zone_ids: Mapped[Any] = mapped_column(JSONB, nullable=False)
    heartbeat_timeout_s: Mapped[int] = mapped_column(Integer, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CameraEvent(Base):
    __tablename__ = "camera_events"
    __table_args__ = (
        Index("ix_camera_events_camera_id_timestamp", "camera_id", "timestamp"),
        Index("ix_camera_events_asset_id", "asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"))
    event_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    confidence: Mapped[float | None] = mapped_column(Double)
    raw_payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    unknown_asset: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class BleEvent(Base):
    __tablename__ = "ble_events"
    __table_args__ = (
        Index("ix_ble_events_tag_id_timestamp", "tag_id", "timestamp"),
        Index("ix_ble_events_asset_id", "asset_id"),
        Index(
            "uq_ble_events_tag_timestamp",
            "tag_id",
            "timestamp",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tag_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"))
    event_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    readings: Mapped[Any] = mapped_column(JSONB, nullable=False)
    raw_payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    unknown_asset: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class FusionDecision(Base):
    __tablename__ = "fusion_decisions"
    __table_args__ = (
        Index("ix_fusion_decisions_asset_id_created_at", "asset_id", "created_at"),
        CheckConstraint(
            "decision_status IN ('confirmed', 'sensor_disagreement', 'stale', 'unknown')",
            name="ck_fusion_decisions_decision_status",
        ),
        CheckConstraint(
            "confidence_band IN ('high', 'medium', 'low', 'stale')",
            name="ck_fusion_decisions_confidence_band",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    decision_status: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Double, nullable=False)
    confidence_band: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_breakdown: Mapped[Any] = mapped_column(JSONB, nullable=False)
    calibration_info: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_links: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    camera_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    ble_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class LocationEstimate(Base):
    __tablename__ = "location_estimates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    fusion_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fusion_decisions.id"))
    x: Mapped[float] = mapped_column(Double, nullable=False)
    y: Mapped[float] = mapped_column(Double, nullable=False)
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False)
    gateway_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ble_quality: Mapped[float] = mapped_column(Double, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AssetCurrentState(Base):
    __tablename__ = "asset_current_state"
    __table_args__ = (
        CheckConstraint(
            "decision_status IN ('confirmed', 'sensor_disagreement', 'stale', 'unknown')",
            name="ck_asset_current_state_decision_status",
        ),
        CheckConstraint(
            "confidence_band IN ('high', 'medium', 'low', 'stale')",
            name="ck_asset_current_state_confidence_band",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, unique=True)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    confidence_band: Mapped[str] = mapped_column(Text, nullable=False)
    decision_status: Mapped[str] = mapped_column(Text, nullable=False)
    last_fusion_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fusion_decisions.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AssetStatusHistory(Base):
    __tablename__ = "asset_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ParLevel(Base):
    __tablename__ = "par_levels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False)
    asset_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_types.id"), nullable=False)
    par_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_zone_id_status", "zone_id", "status"),
        Index(
            "uq_alerts_active_par_deficit_zone_asset_type",
            "zone_id",
            "asset_type_id",
            unique=True,
            postgresql_where=text(
                "alert_type = 'par_deficit' "
                "AND status IN ('open', 'acknowledged', 'dismissed')"
            ),
            sqlite_where=text(
                "alert_type = 'par_deficit' "
                "AND status IN ('open', 'acknowledged', 'dismissed')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"))
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False)
    asset_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_types.id"), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    par_count: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(Text)


class DemandEvent(Base):
    __tablename__ = "demand_events"
    __table_args__ = (Index("ix_demand_events_zone_id_asset_type_id", "zone_id", "asset_type_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False)
    asset_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_types.id"), nullable=False)
    demand_count: Mapped[int] = mapped_column(Integer, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class MovementHistory(Base):
    __tablename__ = "movement_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    from_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    to_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    fusion_decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fusion_decisions.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SensorHeartbeat(Base):
    __tablename__ = "sensor_heartbeats"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    sensor_type: Mapped[str] = mapped_column(Text, nullable=False)
    sensor_id: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class FloorPlan(Base):
    __tablename__ = "floor_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    floor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id"), nullable=False)
    svg_content: Mapped[str] = mapped_column(Text, nullable=False)
    zone_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CoverageFigure(Base):
    __tablename__ = "coverage_figures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    camera_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"))
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False)
    coverage_percent: Mapped[float] = mapped_column(Double, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class WebhookLog(Base):
    __tablename__ = "webhook_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    webhook_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ScenarioRun(Base):
    __tablename__ = "scenario_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    scenario_name: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    inputs: Mapped[Any] = mapped_column(JSONB, nullable=False)
    outputs: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SystemConfig(Base):
    __tablename__ = "system_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
