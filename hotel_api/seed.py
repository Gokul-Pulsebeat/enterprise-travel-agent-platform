"""Idempotent mock data for the hotel service.

Applied at start-up inside the same transaction and advisory lock as the migrations (see
``common.db.migrate_and_seed``). Every insert is ``ON CONFLICT DO NOTHING``, so restarting, or two instances
starting together, never duplicates rows. Rows are inserted in the listed order, so on an empty database
``Delhi Stay`` is hotel id 1 and its offer is offer id 1. Disable with ``SEED_MOCK_DATA=false``.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from hotel_api.database import hotel_offers, hotels

# (name, city, area, rating)
MOCK_HOTELS = [
    ("Delhi Stay", "Delhi", "Connaught Place", 4.2),
    ("Budget Inn Delhi", "Delhi", "Karol Bagh", 3.8),
    ("Sea View Mumbai", "Mumbai", "Marine Drive", 4.6),
    ("Garden City Hotel", "Bengaluru", "Indiranagar", 4.1),
    ("Marina Comfort", "Chennai", "Mylapore", 4.0),
]

# (hotel name, hotel city, check-in, check-out, price per night, rooms available)
MOCK_OFFERS = [
    ("Delhi Stay", "Delhi", date(2026, 6, 10), date(2026, 6, 11), 4200, 5),
    ("Budget Inn Delhi", "Delhi", date(2026, 6, 10), date(2026, 6, 11), 2600, 12),
    ("Sea View Mumbai", "Mumbai", date(2026, 6, 11), date(2026, 6, 12), 7800, 3),
    ("Garden City Hotel", "Bengaluru", date(2026, 6, 12), date(2026, 6, 13), 5100, 7),
    ("Marina Comfort", "Chennai", date(2026, 6, 13), date(2026, 6, 14), 3900, 9),
]


async def seed_mock_data(connection: AsyncConnection) -> None:
    """Insert the properties first, then the offers that point at them."""
    await connection.execute(
        insert(hotels)
        .values(
            [{"name": name, "city": city, "area": area, "rating": rating} for name, city, area, rating in MOCK_HOTELS]
        )
        .on_conflict_do_nothing(index_elements=["name", "city"])
    )

    hotel_ids = {
        (name, city): hotel_id
        for hotel_id, name, city in await connection.execute(select(hotels.c.id, hotels.c.name, hotels.c.city))
    }
    await connection.execute(
        insert(hotel_offers)
        .values(
            [
                {
                    "hotel_id": hotel_ids[(name, city)],
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "price_per_night": price,
                    "rooms_available": rooms,
                }
                for name, city, check_in, check_out, price, rooms in MOCK_OFFERS
            ]
        )
        .on_conflict_do_nothing(index_elements=["hotel_id", "check_in_date", "check_out_date"])
    )
