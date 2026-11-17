"""Create the hotel schema: hotels (properties) and hotel_offers (bookable stay windows).

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

SCHEMA = "hotel"


def upgrade() -> None:
    op.create_table(
        "hotels",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("area", sa.Text(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_hotels"),
        sa.UniqueConstraint("name", "city", name="uq_hotels_name_city"),
        sa.CheckConstraint("rating >= 0 AND rating <= 5", name="ck_hotels_rating_range"),
        schema=SCHEMA,
    )
    # Searches match the city case-insensitively (upper(city) = ...), so index that expression.
    op.create_index("ix_hotels_city_upper", "hotels", [sa.text("upper(city)")], schema=SCHEMA)

    op.create_table(
        "hotel_offers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), nullable=False),
        sa.Column("check_in_date", sa.Date(), nullable=False),
        sa.Column("check_out_date", sa.Date(), nullable=False),
        sa.Column("price_per_night", sa.Integer(), nullable=False),
        sa.Column("rooms_available", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_hotel_offers"),
        sa.ForeignKeyConstraint(
            ["hotel_id"], [f"{SCHEMA}.hotels.id"], name="fk_hotel_offers_hotel_id", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("hotel_id", "check_in_date", "check_out_date", name="uq_hotel_offers_hotel_dates"),
        sa.CheckConstraint("check_out_date > check_in_date", name="ck_hotel_offers_checkout_after_checkin"),
        sa.CheckConstraint("price_per_night >= 0", name="ck_hotel_offers_price_non_negative"),
        sa.CheckConstraint("rooms_available >= 0", name="ck_hotel_offers_rooms_non_negative"),
        schema=SCHEMA,
    )
    op.create_index("ix_hotel_offers_hotel_checkin", "hotel_offers", ["hotel_id", "check_in_date"], schema=SCHEMA)


def downgrade() -> None:
    # Dropping a table drops its indexes; the child table goes first because of the foreign key.
    op.drop_table("hotel_offers", schema=SCHEMA)
    op.drop_table("hotels", schema=SCHEMA)
