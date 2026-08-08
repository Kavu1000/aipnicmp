"""AI-PNICMP ingestion and map API (Layers 2 and 5 of the architecture)."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

app = FastAPI(
    title="AI-PNICMP API",
    description=(
        "National internet coverage mapping platform for Lao PDR. "
        "Receives crowdsourced signal measurements from Android collectors and "
        "serves the aggregated public coverage map."
    ),
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "ai-pnicmp", "docs": "/docs", "api": settings.api_prefix}
