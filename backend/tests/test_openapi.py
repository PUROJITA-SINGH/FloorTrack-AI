import json
from pathlib import Path

from fastapi.routing import APIRoute

from app.main import app

DOCS_OPENAPI_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def test_openapi_spec_version_is_3_1() -> None:
    schema = app.openapi()
    assert schema.get("openapi", "").startswith("3.1")


def test_openapi_spec_matches_registered_routes() -> None:
    schema = app.openapi()
    spec_paths = set(schema.get("paths", {}).keys())

    # Collect all API routes defined on the FastAPI app
    route_paths = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path not in {"/docs", "/redoc", "/openapi.json"}
    }

    assert route_paths.issubset(spec_paths), f"Missing paths in OpenAPI spec: {route_paths - spec_paths}"


def test_checked_in_openapi_spec_matches_app_spec() -> None:
    assert DOCS_OPENAPI_PATH.exists(), "docs/openapi.json must exist"
    with open(DOCS_OPENAPI_PATH, encoding="utf-8") as f:
        checked_in = json.load(f)

    app_spec = app.openapi()
    assert set(checked_in.get("paths", {}).keys()) == set(app_spec.get("paths", {}).keys())
    assert checked_in.get("openapi") == app_spec.get("openapi")


def test_required_endpoints_are_documented() -> None:
    paths = set(app.openapi().get("paths", {}).keys())
    required_paths = {
        "/api/v1/events/ble",
        "/api/v1/events/camera",
        "/api/v1/assets/{asset_id}/operational-status",
        "/api/v1/assets",
        "/api/v1/assets/{asset_id}",
        "/api/v1/assets/{asset_id}/history",
        "/api/v1/inventory",
        "/api/v1/alerts",
        "/api/v1/alerts/{alert_id}/confirm",
        "/api/v1/forecast",
        "/api/v1/cmms/work-orders",
        "/api/v1/webhooks/{channel}",
    }
    assert required_paths.issubset(paths), f"Missing required endpoints: {required_paths - paths}"
