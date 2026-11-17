"""Helpers for tests that talk to a real PostgreSQL server (no SQLite fallback; see TASK-2.1)."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from common.db import build_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _asyncpg_dsn(url_text: str, database: str | None = None) -> str:
    """A plain postgresql:// DSN for asyncpg, optionally pointed at a different database."""
    url = make_url(url_text).set(drivername="postgresql")
    if database is not None:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def _ensure_database(url_text: str, recreate: bool) -> None:
    name = make_url(url_text).database
    # CREATE/DROP DATABASE must be issued from another database, so connect to the maintenance database.
    connection = await asyncpg.connect(_asyncpg_dsn(url_text, database="postgres"), timeout=5)
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if exists and recreate:
            await connection.execute(f"DROP DATABASE {_quote_identifier(name)} WITH (FORCE)")
            exists = False
        if not exists:
            await connection.execute(f"CREATE DATABASE {_quote_identifier(name)}")
    finally:
        await connection.close()


def ensure_database(url_text: str, *, recreate: bool = False) -> None:
    """Create the database named in the URL if it is missing (or drop and recreate it when asked).

    Fails the test run with an actionable message when PostgreSQL cannot be reached, instead of skipping, so a
    broken setup can never look like a pass.
    """
    try:
        asyncio.run(_ensure_database(url_text, recreate))
    except (OSError, asyncpg.PostgresError) as error:
        target = make_url(url_text).set(password="***").render_as_string(hide_password=False)
        pytest.fail(
            f"PostgreSQL is not reachable at {target} ({error!r}).\n"
            "Start it with:  docker compose up -d postgres\n"
            "or point TEST_DATABASE_URL at another server. For a run without a database use:\n"
            '  pytest -m "not db and not integration"',
            pytrace=False,
        )


def run_alembic(service: str, database_url: str, *args: str) -> None:
    """Run the real Alembic CLI for a service (for example ``flight_api``), exercising its env.py CLI path."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", f"{service}/alembic.ini", *args],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed for {service}:\n{result.stdout}\n{result.stderr}"


def fetch_all(database_url: str, sql: str) -> list[tuple]:
    """Run one query and return its rows as tuples."""

    async def _go() -> list[tuple]:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text(sql))
                return [tuple(row) for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def execute_sql(database_url: str, statements: list[str]) -> None:
    """Run statements in one transaction that is always rolled back, so tests never leave rows behind.

    A violated constraint raises ``sqlalchemy.exc.IntegrityError`` from the failing statement.
    """

    async def _go() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:
                for statement in statements:
                    await connection.execute(text(statement))
                await connection.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_go())
