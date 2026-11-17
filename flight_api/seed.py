"""Idempotent mock data for the flight service.

Applied at start-up inside the same transaction and advisory lock as the migrations (see
``common.db.migrate_and_seed``). Every insert is ``ON CONFLICT DO NOTHING``, so restarting, or two instances
starting together, never duplicates rows. Rows are inserted in the listed order, so on an empty database
``AI101`` is flight id 1. Disable with ``SEED_MOCK_DATA=false``.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from flight_api.database import airlines, airports, flights

# (IATA code, name)
MOCK_AIRLINES = [
    ("AI", "Air India"),
    ("6E", "IndiGo"),
    ("UK", "Vistara"),
    ("SG", "SpiceJet"),
]

# (IATA code, city, IANA time zone)
MOCK_AIRPORTS = [
    ("BLR", "Bengaluru", "Asia/Kolkata"),
    ("DEL", "Delhi", "Asia/Kolkata"),
    ("BOM", "Mumbai", "Asia/Kolkata"),
    ("MAA", "Chennai", "Asia/Kolkata"),
]

# (flight number, airline code, origin, destination, departure, arrival, price, seats available)
MOCK_FLIGHTS = [
    ("AI101", "AI", "BLR", "DEL", datetime(2026, 6, 10, 8, 30), datetime(2026, 6, 10, 11, 10), 6800, 12),
    ("6E202", "6E", "BLR", "DEL", datetime(2026, 6, 10, 14, 45), datetime(2026, 6, 10, 17, 30), 5400, 20),
    ("UK811", "UK", "BLR", "BOM", datetime(2026, 6, 11, 9, 15), datetime(2026, 6, 11, 11, 0), 4900, 8),
    ("SG404", "SG", "BOM", "BLR", datetime(2026, 6, 12, 7, 20), datetime(2026, 6, 12, 9, 5), 4300, 15),
    ("6E511", "6E", "BLR", "MAA", datetime(2026, 6, 13, 18, 5), datetime(2026, 6, 13, 19, 5), 3200, 18),
]


async def seed_mock_data(connection: AsyncConnection) -> None:
    """Insert the reference data first (airlines, airports), then the flights that point at them."""
    await connection.execute(
        insert(airlines)
        .values([{"iata_code": code, "name": name} for code, name in MOCK_AIRLINES])
        .on_conflict_do_nothing(index_elements=["iata_code"])
    )
    await connection.execute(
        insert(airports)
        .values([{"iata_code": code, "city": city, "timezone": zone} for code, city, zone in MOCK_AIRPORTS])
        .on_conflict_do_nothing(index_elements=["iata_code"])
    )

    airline_ids = {
        code: airline_id for code, airline_id in await connection.execute(select(airlines.c.iata_code, airlines.c.id))
    }
    await connection.execute(
        insert(flights)
        .values(
            [
                {
                    "flight_number": number,
                    "airline_id": airline_ids[airline_code],
                    "origin_code": origin,
                    "destination_code": destination,
                    "departure_time": departure,
                    "arrival_time": arrival,
                    "price": price,
                    "seats_available": seats,
                }
                for number, airline_code, origin, destination, departure, arrival, price, seats in MOCK_FLIGHTS
            ]
        )
        .on_conflict_do_nothing(index_elements=["flight_number", "departure_time"])
    )
