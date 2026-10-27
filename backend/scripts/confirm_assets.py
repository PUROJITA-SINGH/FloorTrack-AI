import os
import sys
from collections.abc import Mapping
from typing import Any

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def get_assets(client: httpx.Client, base_url: str) -> list[Mapping[str, Any]]:
    response = client.get(f"{base_url}/api/v1/assets")
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, list):
        assets = payload
    elif isinstance(payload, dict):
        assets = payload.get("assets", payload.get("items"))
    else:
        assets = None

    if not isinstance(assets, list) or not all(isinstance(asset, dict) for asset in assets):
        raise ValueError("GET /api/v1/assets must return an array of assets")

    return assets


def confirm_assets(client: httpx.Client, base_url: str) -> int:
    assets = get_assets(client, base_url)
    failures = 0

    for asset in assets:
        asset_id = asset.get("id")
        if not asset_id:
            print(f"FAIL asset without id: {asset!r}")
            failures += 1
            continue

        try:
            response = client.post(
                f"{base_url}/api/v1/assets/{asset_id}/operational-status",
                json={
                    "status": "available",
                    "source": "user",
                    "actor": "demo_admin",
                    "reason": "initial demo confirmation",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            print(f"FAIL {asset_id}: {error}")
            failures += 1
        else:
            print(f"SUCCESS {asset_id}")

    return failures


def main() -> int:
    try:
        with httpx.Client(timeout=30.0) as client:
            failures = confirm_assets(client, API_BASE_URL)
    except (httpx.HTTPError, ValueError) as error:
        print(f"Failed to read assets: {error}", file=sys.stderr)
        return 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
