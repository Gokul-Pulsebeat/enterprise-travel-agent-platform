"""Table definitions for the flight service (schema ``flight`` in the shared Postgres database).

These SQLAlchemy Core definitions mirror migration ``0001``. Queries are built from them, and Alembic uses the
metadata for autogenerate. Always change the schema through a new Alembic revision, never by editing 0001.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.sql import Select

# Every table of this service lives in its own Postgres schema, qualified explicitly in code (the connection's
# search_path is never relied on). Alembic keeps this service's version history in the same schema.
SCHEMA = "flight"

# Advisory-lock key that serializes this service's start-up migrations (the hotel service uses a different key).
MIGRATION_LOCK_KEY = 7_202_601

metadata = MetaData(schema=SCHEMA)

airlines = Table(
    "airlines",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("iata_code", Text, nullable=False),
    Column("name", Text, nullable=False),
    UniqueConstraint("iata_code", name="uq_airlines_iata_code"),
    UniqueConstraint("name", name="uq_airlines_name"),
)

# Airports are keyed by their IATA code: it is what the API and the agent already use, and it keeps the foreign
# key values on flights readable.
airports = Table(
    "airports",
    metadata,
    Column("iata_code", Text, primary_key=True),
    Column("city", Text, nullable=False),
    Column("timezone", Text, nullable=False),
    CheckConstraint("iata_code ~ '^[A-Z]{3}$'", name="ck_airports_iata_code_format"),
)

# One row is one dated flight, the unit that bookings will lock and decrement (TASK-2.3).
flights = Table(
    "flights",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("flight_number", Text, nullable=False),
    Column(
        "airline_id",
        BigInteger,
        ForeignKey("flight.airlines.id", name="fk_flights_airline_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "origin_code",
        Text,
        ForeignKey("flight.airports.iata_code", name="fk_flights_origin_code", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "destination_code",
        Text,
        ForeignKey("flight.airports.iata_code", name="fk_flights_destination_code", ondelete="RESTRICT"),
        nullable=False,
    ),
    # Airport-local wall-clock times (no zone) keep the JSON output identical to the original API.
    Column("departure_time", DateTime, nullable=False),
    Column("arrival_time", DateTime, nullable=False),
    Column("price", Integer, nullable=False),
    Column("seats_available", Integer, nullable=False),
    UniqueConstraint("flight_number", "departure_time", name="uq_flights_number_departure"),
    CheckConstraint("arrival_time > departure_time", name="ck_flights_arrival_after_departure"),
    CheckConstraint("origin_code <> destination_code", name="ck_flights_distinct_airports"),
    CheckConstraint("price >= 0", name="ck_flights_price_non_negative"),
    CheckConstraint("seats_available >= 0", name="ck_flights_seats_non_negative"),
    Index("ix_flights_route_departure", "origin_code", "destination_code", "departure_time"),
)


def flight_select() -> Select:
    """The flat flight shape the REST API returns: each flight joined to its airline's name and code."""
    return select(
        flights.c.id,
        flights.c.flight_number,
        airlines.c.name.label("airline"),
        airlines.c.iata_code.label("airline_code"),
        flights.c.origin_code.label("origin"),
        flights.c.destination_code.label("destination"),
        flights.c.departure_time,
        flights.c.arrival_time,
        flights.c.price,
        flights.c.seats_available,
    ).select_from(flights.join(airlines, flights.c.airline_id == airlines.c.id))
