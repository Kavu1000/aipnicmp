"""Async engine and session dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

def _engine_kwargs() -> dict[str, object]:
    """SQLite (used by the test suite) has no connection pool to size."""
    if settings.database_url.startswith("sqlite"):
        return {}
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}


engine = create_async_engine(settings.database_url, echo=False, **_engine_kwargs())

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


# A view of the same engine — the same pool, the same connections — that does
# not open a transaction around a statement.
#
# A read that runs alone gains nothing from a transaction and pays for it: the
# BEGIN and the ROLLBACK are two extra round trips, which is invisible beside a
# local database and half the response time when the database is reached over a
# tunnel, as it is here. The pool is shared rather than duplicated, so this
# costs no additional connections.
_read_engine = engine.execution_options(isolation_level="AUTOCOMMIT")

ReadSessionLocal = async_sessionmaker(
    _read_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """A session for endpoints that only ever SELECT.

    Deliberately *not* the default. Every write path in this application
    depends on a transaction to make a batch of measurements land or not land
    as one thing, and an engine-wide AUTOCOMMIT would quietly take that away.
    Only routers that read are handed this one.
    """
    async with ReadSessionLocal() as session:
        yield session
