"""Integrity tests: the normalized schema must enforce its constraints in the database itself.

Every case runs in a transaction that is rolled back, so nothing persists. Each violation test has a positive
control (the same statements with valid values succeed), so a failure can only come from the constraint under test.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from tests.db_helpers import execute_sql, run_alembic

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def database_url(migrations_database_url):
    for service in ("flight_api", "hotel_api"):
        run_alembic(service, migrations_database_url, "upgrade", "head")
    return migrations_database_url


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------
FLIGHT_PARENTS = [
    "INSERT INTO flight.airlines (iata_code, name) VALUES ('ZZ', 'Test Air')",
    "INSERT INTO flight.airports (iata_code, city, timezone) VALUES ('AAA', 'Alpha', 'UTC'), ('BBB', 'Bravo', 'UTC')",
]
VALID_AIRLINE = "(SELECT id FROM flight.airlines WHERE iata_code = 'ZZ')"


def flight_insert(
    *,
    airline_id: str = VALID_AIRLINE,
    origin: str = "AAA",
    destination: str = "BBB",
    departure: str = "2026-07-01 08:00:00",
    arrival: str = "2026-07-01 10:00:00",
    price: int = 100,
    seats: int = 5,
) -> str:
    return (
        "INSERT INTO flight.flights (flight_number, airline_id, origin_code, destination_code, "
        "departure_time, arrival_time, price, seats_available) VALUES "
        f"('TS1', {airline_id}, '{origin}', '{destination}', TIMESTAMP '{departure}', TIMESTAMP '{arrival}', "
        f"{price}, {seats})"
    )


def test_a_valid_flight_can_be_inserted(database_url):
    execute_sql(database_url, [*FLIGHT_PARENTS, flight_insert()])


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"airline_id": "999999"}, id="unknown-airline"),
        pytest.param({"origin": "ZZZ"}, id="unknown-origin-airport"),
        pytest.param({"destination": "ZZZ"}, id="unknown-destination-airport"),
        pytest.param({"origin": "AAA", "destination": "AAA"}, id="same-origin-and-destination"),
        pytest.param({"arrival": "2026-07-01 07:00:00"}, id="arrival-before-departure"),
        pytest.param({"price": -1}, id="negative-price"),
        pytest.param({"seats": -1}, id="negative-seats"),
    ],
)
def test_invalid_flights_are_rejected_by_the_database(database_url, overrides):
    with pytest.raises(IntegrityError):
        execute_sql(database_url, [*FLIGHT_PARENTS, flight_insert(**overrides)])


def test_the_same_flight_number_cannot_depart_twice_at_the_same_time(database_url):
    with pytest.raises(IntegrityError):
        execute_sql(database_url, [*FLIGHT_PARENTS, flight_insert(), flight_insert()])


def test_airline_and_airport_in_use_cannot_be_deleted(database_url):
    with pytest.raises(IntegrityError):
        execute_sql(
            database_url, [*FLIGHT_PARENTS, flight_insert(), "DELETE FROM flight.airlines WHERE iata_code = 'ZZ'"]
        )
    with pytest.raises(IntegrityError):
        execute_sql(
            database_url, [*FLIGHT_PARENTS, flight_insert(), "DELETE FROM flight.airports WHERE iata_code = 'AAA'"]
        )


@pytest.mark.parametrize("code", ["ab", "ABCD", "A1C", ""])
def test_airport_codes_must_be_three_uppercase_letters(database_url, code):
    with pytest.raises(IntegrityError):
        execute_sql(
            database_url, [f"INSERT INTO flight.airports (iata_code, city, timezone) VALUES ('{code}', 'X', 'UTC')"]
        )


def test_airline_codes_and_names_are_unique(database_url):
    with pytest.raises(IntegrityError):
        execute_sql(
            database_url,
            [
                "INSERT INTO flight.airlines (iata_code, name) VALUES ('ZZ', 'Test Air')",
                "INSERT INTO flight.airlines (iata_code, name) VALUES ('ZZ', 'Other Name')",
            ],
        )


# ---------------------------------------------------------------------------
# Hotels
# ---------------------------------------------------------------------------
HOTEL_PARENT = "INSERT INTO hotel.hotels (name, city, area, rating) VALUES ('Test Inn', 'Testville', 'Centre', 4.0)"
VALID_HOTEL = "(SELECT id FROM hotel.hotels WHERE name = 'Test Inn')"


def offer_insert(
    *,
    hotel_id: str = VALID_HOTEL,
    check_in: str = "2026-07-01",
    check_out: str = "2026-07-02",
    price: int = 100,
    rooms: int = 5,
) -> str:
    return (
        "INSERT INTO hotel.hotel_offers (hotel_id, check_in_date, check_out_date, price_per_night, rooms_available) "
        f"VALUES ({hotel_id}, DATE '{check_in}', DATE '{check_out}', {price}, {rooms})"
    )


def test_a_valid_hotel_offer_can_be_inserted(database_url):
    execute_sql(database_url, [HOTEL_PARENT, offer_insert()])


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"hotel_id": "999999"}, id="unknown-hotel"),
        pytest.param({"check_out": "2026-07-01"}, id="checkout-equals-checkin"),
        pytest.param({"check_out": "2026-06-30"}, id="checkout-before-checkin"),
        pytest.param({"price": -1}, id="negative-price"),
        pytest.param({"rooms": -1}, id="negative-rooms"),
    ],
)
def test_invalid_hotel_offers_are_rejected_by_the_database(database_url, overrides):
    with pytest.raises(IntegrityError):
        execute_sql(database_url, [HOTEL_PARENT, offer_insert(**overrides)])


@pytest.mark.parametrize("rating", [-0.1, 5.1, 6])
def test_hotel_ratings_must_be_between_zero_and_five(database_url, rating):
    with pytest.raises(IntegrityError):
        execute_sql(
            database_url,
            [f"INSERT INTO hotel.hotels (name, city, area, rating) VALUES ('Bad', 'Testville', 'Centre', {rating})"],
        )


def test_a_hotel_cannot_be_listed_twice_in_the_same_city(database_url):
    with pytest.raises(IntegrityError):
        execute_sql(database_url, [HOTEL_PARENT, HOTEL_PARENT])


def test_the_same_offer_window_cannot_be_listed_twice(database_url):
    with pytest.raises(IntegrityError):
        execute_sql(database_url, [HOTEL_PARENT, offer_insert(), offer_insert()])


def test_a_hotel_with_offers_cannot_be_deleted(database_url):
    with pytest.raises(IntegrityError):
        execute_sql(database_url, [HOTEL_PARENT, offer_insert(), "DELETE FROM hotel.hotels WHERE name = 'Test Inn'"])
