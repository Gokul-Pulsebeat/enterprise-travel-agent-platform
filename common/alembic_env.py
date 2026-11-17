"""Shared Alembic environment logic for the per-service migration folders.

Each service's ``migrations/env.py`` is a three-line file that calls :func:`run_migrations`. Two modes:

- **Programmatic (service start-up):** ``common.db.migrate_and_seed`` passes its open connection through
  ``config.attributes["connection"]``, so migrations run on the connection that already holds the advisory lock,
  inside the already-running event loop.
- **CLI** (``alembic -c flight_api/alembic.ini upgrade head``): no connection is passed, so this module builds
  its own async engine from ``DATABASE_URL`` and runs the migrations on it.
"""

import asyncio
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.schema import MetaData

from common.db import build_engine


async def _run_on_own_engine(callback: Callable[[Connection], None]) -> None:
    engine = build_engine()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(callback)
    finally:
        await engine.dispose()


def run_migrations(context, *, schema: str, metadata: MetaData) -> None:
    """Run the migrations for one service, keeping everything inside that service's Postgres schema."""
    if context.is_offline_mode():
        raise RuntimeError("Offline (--sql) migrations are not supported; run against a live database.")

    def include_object(obj, name, type_, reflected, compare_to) -> bool:
        # Autogenerate only this service's schema; never propose changes to another service's tables.
        if type_ == "table":
            return obj.schema == schema
        return True

    def do_run_migrations(connection: Connection) -> None:
        # The version table lives in the service's schema, which therefore has to exist before Alembic starts.
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        context.configure(
            connection=connection,
            target_metadata=metadata,
            version_table_schema=schema,
            include_schemas=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()

    shared_connection = context.config.attributes.get("connection")
    if shared_connection is not None:
        do_run_migrations(shared_connection)
    else:
        asyncio.run(_run_on_own_engine(do_run_migrations))
