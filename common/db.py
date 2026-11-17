"""Shared database plumbing for the REST services: SQLAlchemy 2.0 (async) + asyncpg + Alembic.

flight_api and hotel_api both use this module so that URL handling, pool settings, readiness checks and the
guarded migration runner behave identically.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

# Local development default: the Postgres service from docker-compose.yml. In Cloud Run the DATABASE_URL secret
# (the Neon connection string injected by Terraform) always overrides it.
DEFAULT_DATABASE_URL = "postgresql://travel:travel_dev_password@127.0.0.1:5432/travel_agent"

# Largest value a Postgres BIGINT can hold. IDs above it cannot exist, so looking one up is a plain 404.
MAX_BIGINT = 2**63 - 1

# How long a starting instance waits for another instance that is migrating the same schema.
MIGRATION_LOCK_TIMEOUT = "30s"

_ASYNC_DRIVER = "postgresql+asyncpg"
_ACCEPTED_DRIVERS = {"postgres", "postgresql", _ASYNC_DRIVER}

# Connection-string options that libpq understands but asyncpg does not implement.
_UNSUPPORTED_QUERY_OPTIONS = {"channel_binding"}

# A seed function receives the connection that holds the migration lock and runs inside its transaction.
SeedFunction = Callable[[AsyncConnection], Awaitable[None]]


def get_database_url() -> str:
    """Return the configured connection string (DATABASE_URL), or the local development default."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment variable (1/true/yes/on are true; anything else is false)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def normalize_database_url(raw_url: str) -> URL:
    """Turn a standard Postgres URL into one SQLAlchemy's asyncpg driver accepts.

    Managed providers such as Neon hand out URIs like
    ``postgresql://user:pass@host/db?sslmode=require&channel_binding=require``. SQLAlchemy forwards unknown query
    parameters to asyncpg, which rejects ``sslmode`` and does not implement ``channel_binding``. This function:

    - rewrites the scheme (``postgres``/``postgresql``) to ``postgresql+asyncpg``,
    - maps ``sslmode=<mode>`` to asyncpg's ``ssl=<mode>``,
    - drops options asyncpg cannot handle.
    """
    url = make_url(raw_url)
    if url.drivername not in _ACCEPTED_DRIVERS:
        # Only the scheme is reported, so the message can never leak the password.
        raise ValueError(f"Unsupported DATABASE_URL scheme {url.drivername!r}; expected postgresql://")

    query = {key: value if isinstance(value, str) else value[-1] for key, value in url.query.items()}
    ssl_mode = query.pop("sslmode", None)
    for option in _UNSUPPORTED_QUERY_OPTIONS:
        query.pop(option, None)
    if ssl_mode is not None and "ssl" not in query:
        query["ssl"] = ssl_mode

    return url.set(drivername=_ASYNC_DRIVER, query=query)


def build_engine(url: Optional[str] = None) -> AsyncEngine:
    """Create an async engine with a small pool suited to Cloud Run and Neon.

    Pre-ping and recycling matter because Neon suspends idle compute and silently drops connections. Create the
    engine inside the application's lifespan handler, never at import time, so it binds to the right event loop.
    """
    return create_async_engine(
        normalize_database_url(url or get_database_url()),
        pool_size=_env_int("DB_POOL_SIZE", 3),
        max_overflow=_env_int("DB_MAX_OVERFLOW", 2),
        pool_pre_ping=True,
        pool_recycle=_env_int("DB_POOL_RECYCLE_SECONDS", 300),
    )


async def check_ready(engine: AsyncEngine, timeout_seconds: float = 5.0) -> bool:
    """Return True when a trivial query succeeds within the timeout (used by the /ready endpoints)."""
    try:
        async with asyncio.timeout(timeout_seconds):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def get_connection(request: Request) -> AsyncIterator[AsyncConnection]:
    """FastAPI dependency: one pooled connection per request, returned to the pool afterwards."""
    async with request.app.state.engine.connect() as connection:
        yield connection


def _upgrade_to_head(connection, alembic_config: Config) -> None:
    # Runs inside AsyncConnection.run_sync, so `connection` is the synchronous view of the async connection.
    # Alembic's env.py picks it up from config.attributes and uses it instead of opening its own.
    alembic_config.attributes["connection"] = connection
    command.upgrade(alembic_config, "head")


async def migrate_and_seed(
    engine: AsyncEngine,
    *,
    migrations_dir: Path,
    lock_key: int,
    seed: Optional[SeedFunction] = None,
) -> None:
    """Apply pending migrations, then seed, as one transaction guarded by a Postgres advisory lock.

    Several Cloud Run instances can start at the same moment. The transaction-scoped advisory lock serializes
    them: the first one migrates and seeds, the others wait, then find nothing left to do. The lock is released
    automatically on commit or rollback, so a crashed instance can never leave it held. If anything fails the
    transaction rolls back and the exception propagates, so the service refuses to start.
    """
    alembic_config = Config()
    alembic_config.set_main_option("script_location", migrations_dir.as_posix())

    async with engine.begin() as connection:
        await connection.execute(text(f"SET LOCAL lock_timeout = '{MIGRATION_LOCK_TIMEOUT}'"))
        await connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        await connection.run_sync(_upgrade_to_head, alembic_config)
        if seed is not None:
            await seed(connection)
