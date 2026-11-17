"""Shared pytest fixtures: a real PostgreSQL test database.

Local default: the Postgres service from docker-compose.yml (``docker compose up -d postgres``). The tests use their
own databases, never the development one:

- ``travel_agent_test`` for the API tests and the end-to-end tests,
- ``travel_agent_test_migrations`` (recreated empty every session) for the migration and integrity tests, so every
  run exercises the full migration path from zero.

Point ``TEST_DATABASE_URL`` at another server to override (CI uses a service container).
"""

import os

import pytest
from sqlalchemy.engine import make_url

from tests.db_helpers import ensure_database

DEFAULT_TEST_DATABASE_URL = "postgresql://travel:travel_dev_password@127.0.0.1:5432/travel_agent_test"


@pytest.fixture(scope="session")
def postgres_url():
    """URL of the shared test database. Also exported as DATABASE_URL so in-process apps and the uvicorn
    subprocesses started by the end-to-end tests connect to it."""
    url = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    ensure_database(url)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        yield url


@pytest.fixture(scope="session")
def migrations_database_url(postgres_url):
    """URL of a database that is dropped and recreated empty at the start of every test session."""
    base = make_url(postgres_url)
    url = base.set(database=f"{base.database}_migrations").render_as_string(hide_password=False)
    ensure_database(url, recreate=True)
    return url
