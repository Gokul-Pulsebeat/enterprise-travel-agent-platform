"""Create the flight schema: airlines, airports and flights.

Revision ID: 0001
Revises:
Create Date: 2026-11-16

Written by hand and fully explicit on purpose: a migration must keep producing the same schema even after the
application's table definitions change, so it never imports them.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "flight"


def upgrade() -> None:
    op.create_table(
        "airlines",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("iata_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_airlines"),
        sa.UniqueConstraint("iata_code", name="uq_airlines_iata_code"),
        sa.UniqueConstraint("name", name="uq_airlines_name"),
        schema=SCHEMA,
    )

    op.create_table(
        "airports",
        sa.Column("iata_code", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("iata_code", name="pk_airports"),
        sa.CheckConstraint("iata_code ~ '^[A-Z]{3}$'", name="ck_airports_iata_code_format"),
        schema=SCHEMA,
    )

    op.create_table(
        "flights",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("flight_number", sa.Text(), nullable=False),
        sa.Column("airline_id", sa.BigInteger(), nullable=False),
        sa.Column("origin_code", sa.Text(), nullable=False),
        sa.Column("destination_code", sa.Text(), nullable=False),
        sa.Column("departure_time", sa.DateTime(), nullable=False),
        sa.Column("arrival_time", sa.DateTime(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("seats_available", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_flights"),
        sa.ForeignKeyConstraint(
            ["airline_id"], [f"{SCHEMA}.airlines.id"], name="fk_flights_airline_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["origin_code"], [f"{SCHEMA}.airports.iata_code"], name="fk_flights_origin_code", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["destination_code"],
            [f"{SCHEMA}.airports.iata_code"],
            name="fk_flights_destination_code",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("flight_number", "departure_time", name="uq_flights_number_departure"),
        sa.CheckConstraint("arrival_time > departure_time", name="ck_flights_arrival_after_departure"),
        sa.CheckConstraint("origin_code <> destination_code", name="ck_flights_distinct_airports"),
        sa.CheckConstraint("price >= 0", name="ck_flights_price_non_negative"),
        sa.CheckConstraint("seats_available >= 0", name="ck_flights_seats_non_negative"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flights_route_departure",
        "flights",
        ["origin_code", "destination_code", "departure_time"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Dropping a table drops its indexes; children go first because of the foreign keys.
    op.drop_table("flights", schema=SCHEMA)
    op.drop_table("airports", schema=SCHEMA)
    op.drop_table("airlines", schema=SCHEMA)
