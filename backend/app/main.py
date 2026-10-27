from contextlib import asynccontextmanager
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import initialize_database
from app.routers.assets import router as assets_router
from app.routers.alerts import router as alerts_router
from app.routers.admin import router as admin_router
from app.routers.events import router as events_router
from app.routers.forecast import router as forecast_router
from app.routers.fusion import router as fusion_router
from app.routers.inventory import router as inventory_router
from app.routers.integrations import router as integrations_router
from app.routers.sensors import router as sensors_router
from app.routers.simulator import router as simulator_router
from app.routers.zones import router as zones_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    from scripts.seed import seed_database

    seed_database()
    yield


app = FastAPI(
    title="FloorTrack AI",
    description="Local, simulated, zone-level asset intelligence and inventory demo.",
    version="1.0.0",
    openapi_version="3.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter()


@api_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(forecast_router, prefix="/api/v1")
app.include_router(fusion_router, prefix="/api/v1")
app.include_router(sensors_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1/alerts")
app.include_router(admin_router, prefix="/api/v1/admin")
app.include_router(inventory_router, prefix="/api/v1/inventory")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(simulator_router, prefix="/api/v1/simulator")
app.include_router(zones_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1/assets")
