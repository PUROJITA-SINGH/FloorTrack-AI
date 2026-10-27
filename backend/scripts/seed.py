from datetime import date, timedelta
import os
from pathlib import Path
import sys

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, SessionLocal
from app.models import (
    Asset,
    AssetType,
    Camera,
    DemandEvent,
    Facility,
    Floor,
    FloorPlan,
    Gateway,
    ParLevel,
    Tag,
    Zone,
)

ZONES = (
    ("Ward A", "ward", [[0, 0], [30, 0], [30, 30], [0, 30]]),
    ("Ward B", "ward", [[35, 0], [65, 0], [65, 30], [35, 30]]),
    ("Corridor 1", "corridor", [[0, 35], [100, 35], [100, 50], [0, 50]]),
    ("Storage", "storage", [[0, 55], [30, 55], [30, 85], [0, 85]]),
    ("Maintenance", "maintenance", [[35, 55], [65, 55], [65, 85], [35, 85]]),
    ("Nurse Station", "station", [[70, 55], [100, 55], [100, 85], [70, 85]]),
)

FLOOR_PLAN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect x="0" y="0" width="30" height="30" fill="#e8f2ed" stroke="#334155"/>
  <rect x="35" y="0" width="30" height="30" fill="#e8f2ed" stroke="#334155"/>
  <rect x="0" y="35" width="100" height="15" fill="#f1f5f9" stroke="#334155"/>
  <rect x="0" y="55" width="30" height="30" fill="#fef3c7" stroke="#334155"/>
  <rect x="35" y="55" width="30" height="30" fill="#fee2e2" stroke="#334155"/>
  <rect x="70" y="55" width="30" height="30" fill="#dbeafe" stroke="#334155"/>
</svg>"""

CAMERA_COVERAGE = (
    ("CAM-1", ("Ward A", "Corridor 1")),
    ("CAM-2", ("Ward B", "Corridor 1")),
    ("CAM-3", ("Storage", "Maintenance", "Nurse Station")),
)


def seed_database(*, reset: bool = False) -> None:
    if reset and os.getenv("ALLOW_SEED") != "1":
        raise SystemExit("Refusing to reset without ALLOW_SEED=1")

    with SessionLocal() as session:
        has_facility = session.scalar(select(Facility.id).limit(1)) is not None
        if has_facility and not reset:
            return
        if reset:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())

        facility = Facility(name="City Hospital")
        session.add(facility)
        session.flush()

        floor = Floor(
            facility_id=facility.id,
            name="Floor 1",
            floor_number=1,
            svg_path="floor-1.svg",
        )
        session.add(floor)
        session.flush()

        zones = {
            name: Zone(
                floor_id=floor.id,
                name=name,
                zone_type=zone_type,
                polygon_json=polygon,
            )
            for name, zone_type, polygon in ZONES
        }
        session.add_all(zones.values())
        session.flush()

        session.add(
            FloorPlan(
                floor_id=floor.id,
                svg_content=FLOOR_PLAN_SVG,
                zone_json={
                    name: {"type": zone.zone_type, "polygon": zone.polygon_json}
                    for name, zone in zones.items()
                },
            )
        )

        asset_type = AssetType(name="Infusion Pump")
        session.add(asset_type)
        session.flush()

        asset_numbers = [*range(1, 13), 42]
        assets = [
            Asset(
                code=f"P-{number:03d}",
                serial_number=f"SN-{number:03d}",
                qr_code=f"QR-{number:03d}",
                asset_type_id=asset_type.id,
                floor_id=floor.id,
                current_zone_id=None,
                operational_status="status_unknown",
                status_source="workflow_adapter",
                status_actor="seed.py",
                status_reason="initial seed state",
            )
            for number in asset_numbers
        ]
        session.add_all(assets)
        session.flush()
        session.add_all(
            [
                Tag(
                    asset_id=asset.id,
                    tag_type="ble",
                    tag_value=f"TAG-{number:03d}",
                )
                for number, asset in zip(asset_numbers, assets, strict=True)
            ]
        )

        gateway_positions = ((10, 10), (90, 10), (10, 90), (90, 90))
        session.add_all(
            [
                Gateway(
                    floor_id=floor.id,
                    name=f"GW-{number}",
                    x=x,
                    y=y,
                    heartbeat_timeout_s=60,
                    status="online",
                )
                for number, (x, y) in enumerate(gateway_positions, start=1)
            ]
        )

        session.add_all(
            [
                Camera(
                    floor_id=floor.id,
                    name=name,
                    coverage_zone_ids=[str(zones[zone_name].id) for zone_name in covered_zones],
                    heartbeat_timeout_s=60,
                    status="online",
                )
                for name, covered_zones in CAMERA_COVERAGE
            ]
        )

        session.add_all(
            [
                ParLevel(zone_id=zones[zone_name].id, asset_type_id=asset_type.id, par_count=count)
                for zone_name, count in (("Ward A", 10), ("Ward B", 8), ("Storage", 5))
            ]
        )

        demand_zones = ("Ward A", "Ward B", "Corridor 1", "Storage", "Maintenance", "Nurse Station")
        today = date.today()
        session.add_all(
            [
                DemandEvent(
                    zone_id=zones[demand_zones[index % len(demand_zones)]].id,
                    asset_type_id=asset_type.id,
                    demand_count=1 + index % 4,
                    event_date=today - timedelta(days=9 - index),
                )
                for index in range(10)
            ]
        )

        session.commit()

    print("Seeded City Hospital with one floor, six zones, 13 unknown-status pumps, 13 BLE tags (including P-042/TAG-042), four gateways, three cameras, three PAR levels, and 10 demand events.")


if __name__ == "__main__":
    seed_database(reset=os.getenv("ALLOW_SEED") == "1")
