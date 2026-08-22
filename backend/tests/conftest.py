from __future__ import annotations

import base64
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Must be set before app.core.config is imported anywhere.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENV", "test")

from app.api.v1.public import _TILE_CACHE  # noqa: E402
from app.db.session import get_read_session, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.schemas.measurement import MeasurementIn  # noqa: E402
from app.services.signing import canonical_message  # noqa: E402

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# Somewhere on Route 13 north of Luang Prabang — inside the survey area.
BASE_LAT = 19.8845
BASE_LON = 102.1350


@pytest.fixture(autouse=True)
def _empty_public_tile_cache() -> None:
    """The public tile cache lives for the life of the process.

    That is right in a server and wrong in a test run, where the next test
    builds a different world behind the same viewport — without this, one
    test's hexagons would be served to another and the failure would look
    like a query bug.
    """
    _TILE_CACHE.clear()


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """A fresh in-memory schema per test.

    SQLite stands in for Postgres for everything except the PostGIS generated
    column and the percentile aggregation, which are exercised separately
    against the real database.
    """
    engine = create_async_engine(TEST_DB_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s

    await engine.dispose()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """A signed-in super admin.

    Most tests are about coverage, not about who may see it, so the default
    client is authenticated and the gate is tested separately by ``anon_client``
    below. Overriding the dependency rather than minting a real session keeps
    every other test free of Google.
    """
    from app.models.user import ROLE_SUPER_ADMIN, STATUS_APPROVED, User
    from app.services.auth import require_user

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _test_user() -> User:
        return User(
            id=1,
            google_sub="test-sub",
            email="tester@example.com",
            name="Test Super Admin",
            role=ROLE_SUPER_ADMIN,
            status=STATUS_APPROVED,
        )

    app.dependency_overrides[get_session] = _override
    # The public router asks for the read-only session; in a test it is the
    # same one, so that a fixture setting data up through `get_session` is
    # visible to the endpoint reading it back.
    app.dependency_overrides[get_read_session] = _override
    app.dependency_overrides[require_user] = _test_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Nobody signed in, and the real gate in place.

    HTTPS base url because the session cookie is marked Secure outside
    development, and a client on plain http would silently drop it — which
    would make a working sign-in look broken.
    """
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def device_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def public_key_b64(device_key: Ed25519PrivateKey) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    raw = device_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def make_record(
    *,
    record_id: str = "rec-00000001",
    minutes_ago: int = 30,
    lat: float = BASE_LAT,
    lon: float = BASE_LON,
    registered: bool = True,
    network_type: str | None = "LTE",
    rsrp: float | None = -95.0,
    cells: int = 3,
    gps_accuracy_m: float | None = 8.0,
    **overrides: object,
) -> dict:
    """Build a wire-format record. Kept as a dict so tests exercise the same
    JSON path a phone would."""
    captured = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    neighbours = [
        {"radio": "LTE", "mcc": "457", "mnc": "01", "cid": 10_000 + i, "pci_psc": 100 + i}
        for i in range(max(cells - 1, 0))
    ]
    payload: dict = {
        "client_record_id": record_id,
        "captured_at": captured.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "lat": lat,
        "lon": lon,
        "gps_accuracy_m": gps_accuracy_m,
        "registered": registered,
        "network_type": network_type,
        "operator": {"mcc": "457", "mnc": "01", "name": "LTC"},
        "signal": {"rsrp_dbm": rsrp, "rsrq_db": -11.0, "sinr_db": 8.0, "level": 3},
        "serving_cell": (
            {"radio": "LTE", "mcc": "457", "mnc": "01", "cid": 9999, "is_registered": True}
            if cells > 0
            else None
        ),
        "neighbor_cells": neighbours,
    }
    payload.update(overrides)
    return payload


def sign_record(record: dict, key: Ed25519PrivateKey) -> dict:
    """Sign exactly as the Android client will: over the canonical form, at
    capture time."""
    parsed = MeasurementIn.model_validate(record)
    signature = key.sign(canonical_message(parsed))
    return {**record, "signature": base64.b64encode(signature).decode()}
