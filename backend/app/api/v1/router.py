from fastapi import APIRouter

from app.api.v1 import admin, areas, dashboard, devices, health, ingest, reports, sites, tiles

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(admin.router)
api_router.include_router(areas.router)
api_router.include_router(dashboard.router)
api_router.include_router(devices.router)
api_router.include_router(ingest.router)
api_router.include_router(tiles.router)
api_router.include_router(reports.router)
api_router.include_router(sites.router)
