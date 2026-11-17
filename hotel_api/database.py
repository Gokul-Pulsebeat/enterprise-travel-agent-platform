"""Table definitions for the hotel service (schema ``hotel`` in the shared Postgres database).

These SQLAlchemy Core definitions mirror migration ``0001``. Queries are built from them, and Alembic uses the
metadata for autogenerate. Always change the schema through a new Alembic revision, never by editing 0001.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.sql import Select

# Every table of this service lives in its own Postgres schema, qualified explicitly in code (the connection's
# search_path is never relied on). Alembic keeps this service's version history in the same schema.
SCHEMA = "hotel"

# Advisory-lock key that serializes this service's start-up migrations (the flight service uses a different key).
MIGRATION_LOCK_KEY = 7_202_602

metadata = MetaData(schema=SCHEMA)

# The property itself: what stays true regardless of which dates are on offer.
hotels = Table(
    "hotels",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("name", Text, nullable=False),
    Column("city", Text, nullable=False),
    Column("area", Text, nullable=False),
    Column("rating", Float, nullable=False),
    UniqueConstraint("name", "city", name="uq_hotels_name_city"),
    CheckConstraint("rating >= 0 AND rating <= 5", name="ck_hotels_rating_range"),
)
Index("ix_hotels_city_upper", func.upper(hotels.c.city))

# A bookable stay window with a price and an inventory count. This is the unit that bookings will lock and
# decrement (TASK-2.3), and the `id` the REST API exposes for a hotel result.
hotel_offers = Table(
    "hotel_offers",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column(
        "hotel_id",
        BigInteger,
        ForeignKey("hotel.hotels.id", name="fk_hotel_offers_hotel_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("check_in_date", Date, nullable=False),
    Column("check_out_date", Date, nullable=False),
    Column("price_per_night", Integer, nullable=False),
    Column("rooms_available", Integer, nullable=False),
    UniqueConstraint("hotel_id", "check_in_date", "check_out_date", name="uq_hotel_offers_hotel_dates"),
    CheckConstraint("check_out_date > check_in_date", name="ck_hotel_offers_checkout_after_checkin"),
    CheckConstraint("price_per_night >= 0", name="ck_hotel_offers_price_non_negative"),
    CheckConstraint("rooms_available >= 0", name="ck_hotel_offers_rooms_non_negative"),
    Index("ix_hotel_offers_hotel_checkin", "hotel_id", "check_in_date"),
)


def offer_select() -> Select:
    """The flat hotel shape the REST API returns: each offer joined to its property."""
    return select(
        hotel_offers.c.id,
        hotel_offers.c.hotel_id,
        hotels.c.name,
        hotels.c.city,
        hotels.c.area,
        hotel_offers.c.check_in_date,
        hotel_offers.c.check_out_date,
        hotel_offers.c.price_per_night,
        hotel_offers.c.rooms_available,
        hotels.c.rating,
    ).select_from(hotel_offers.join(hotels, hotel_offers.c.hotel_id == hotels.c.id))
