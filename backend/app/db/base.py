"""Declarative base and shared column conventions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, MetaData
from sqlalchemy.orm import DeclarativeBase, mapped_column

# SQLite only auto-increments a column declared INTEGER PRIMARY KEY, so the
# test suite cannot run against BIGINT keys without this variant. Postgres
# still gets BIGINT, which the measurement table will need.
BigIntPk = BigInteger().with_variant(Integer, "sqlite")

# Explicit naming so Alembic autogenerate produces stable, reversible names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_column(**kwargs: object):
    """A timezone-aware timestamp. Everything in this system is stored in UTC:
    measurements are compared across provinces and uploaded hours after capture,
    so a local-time column would be a bug waiting to happen."""
    return mapped_column(DateTime(timezone=True), **kwargs)  # type: ignore[arg-type]
