"""AI-PNICMP ingestion and map API (Layers 2 and 5 of the architecture)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import engine

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Open one database connection before the first request needs one.

    Opening a connection is not free and, in this deployment, not fast: the
    database is reached over a tunnel, so the handshake costs several round
    trips and the *first* request to arrive after a restart was paying all of
    them — seconds, spent before the query that answers it has even been sent.
    Doing it here moves that cost to startup, where nobody is waiting.

    A failure is logged and swallowed. The pool will simply connect on demand
    as it did before; a database that is briefly unreachable at boot must not
    stop the API from starting, because /health is one of the things somebody
    would then be unable to ask.
    """
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception:  # noqa: BLE001 - see docstring
        logging.getLogger(__name__).warning("could not warm the connection pool", exc_info=True)
    yield


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
    lifespan=lifespan,
)

# Coverage responses are GeoJSON: thousands of repeated property names and
# coordinates that share their leading digits, which compresses by roughly ten
# to one. The map fetches a fresh one on every viewport, and a good part of
# this country reads the map over mobile data — the same connection the map is
# reporting on.
app.add_middleware(GZipMiddleware, minimum_size=1024)

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
