"""Migration tests: run the real Alembic CLI against a database that is recreated empty every session.

Together with the API tests (which migrate in the app's lifespan) this covers both migration entry points.
"""

import pytest

from tests.db_helpers import fetch_all, run_alembic

pytestmark = pytest.mark.db

# service folder -> (Postgres schema, tables it owns)
SERVICES = {
    "flight_api": ("flight", {"airlines", "airports", "flights"}),
    "hotel_api": ("hotel", {"hotels", "hotel_offers"}),
}


def tables_in(database_url: str, schema: str) -> set[str]:
    rows = fetch_all(
        database_url,
        f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema}'",
    )
    return {name for (name,) in rows}


def test_upgrade_creates_each_services_schema_tables_and_own_version_history(migrations_database_url):
    for service, (schema, tables) in SERVICES.items():
        run_alembic(service, migrations_database_url, "upgrade", "head")

        present = tables_in(migrations_database_url, schema)
        assert tables <= present
        # The version table lives in the service's own schema, so the two histories never interfere.
        assert "alembic_version" in present
        assert fetch_all(migrations_database_url, f"SELECT version_num FROM {schema}.alembic_version") == [("0001",)]


def test_upgrade_is_idempotent(migrations_database_url):
    for service in SERVICES:
        run_alembic(service, migrations_database_url, "upgrade", "head")
        run_alembic(service, migrations_database_url, "upgrade", "head")


def test_services_do_not_create_tables_in_each_others_schemas(migrations_database_url):
    for service in SERVICES:
        run_alembic(service, migrations_database_url, "upgrade", "head")

    assert not (SERVICES["hotel_api"][1] & tables_in(migrations_database_url, "flight"))
    assert not (SERVICES["flight_api"][1] & tables_in(migrations_database_url, "hotel"))


def test_downgrade_and_upgrade_round_trip_leaves_the_other_service_untouched(migrations_database_url):
    flight_tables = SERVICES["flight_api"][1]
    hotel_tables = SERVICES["hotel_api"][1]
    for service in SERVICES:
        run_alembic(service, migrations_database_url, "upgrade", "head")

    run_alembic("flight_api", migrations_database_url, "downgrade", "base")
    assert not (flight_tables & tables_in(migrations_database_url, "flight"))
    assert hotel_tables <= tables_in(migrations_database_url, "hotel")

    run_alembic("flight_api", migrations_database_url, "upgrade", "head")
    assert flight_tables <= tables_in(migrations_database_url, "flight")
    assert hotel_tables <= tables_in(migrations_database_url, "hotel")


def test_the_current_revision_is_reported_per_service(migrations_database_url):
    for service in SERVICES:
        run_alembic(service, migrations_database_url, "upgrade", "head")
        run_alembic(service, migrations_database_url, "current")
