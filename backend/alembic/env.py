from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.models import Base  # noqa: F401  (imports every model into the metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The URL is used directly rather than written into the Alembic config.
# alembic.ini is parsed by configparser with interpolation enabled, so a URL
# containing a percent-encoded character — which any password with an "@" or a
# ":" must have — raises "invalid interpolation syntax" before a single
# migration runs.
DATABASE_URL = settings.database_url_sync


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Keep PostGIS's own bookkeeping out of autogenerate."""
    if type_ == "table" and name in {"spatial_ref_sys", "geography_columns", "geometry_columns"}:
        return False
    # The geometry column is added conditionally by migration 0002 and is not
    # present in the ORM models, so autogenerate must not offer to drop it.
    if type_ == "column" and name == "geom":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
