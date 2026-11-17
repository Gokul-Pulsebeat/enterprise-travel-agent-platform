"""Tests for the flight REST API against a real PostgreSQL database (migrations and seed run in the lifespan)."""

import pytest
from fastapi.testclient import TestClient

from flight_api.app import app

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def client(postgres_url):
    # Using TestClient as a context manager runs the app's lifespan: it creates the engine, applies the Alembic
    # migrations and seeds the mock data, exactly as it does in production.
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_the_database_answers(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_list_flights(client):
    response = client.get("/flights")
    assert response.status_code == 200
    flights = response.json()
    assert isinstance(flights, list)
    assert len(flights) == 5
    expected_keys = {
        "id",
        "flight_number",
        "airline",
        "origin",
        "destination",
        "departure_time",
        "arrival_time",
        "price",
        "seats_available",
    }
    assert expected_keys <= set(flights[0])
    # Results are ordered by departure time, earliest first.
    departures = [f["departure_time"] for f in flights]
    assert departures == sorted(departures)


def test_flights_keep_the_original_json_formats(client):
    flight = client.get("/flights/1").json()
    # Timestamps are plain ISO strings without a UTC offset, because the agent slices departure_time[:10].
    assert flight["departure_time"] == "2026-06-10T08:30:00"
    assert flight["arrival_time"] == "2026-06-10T11:10:00"
    assert isinstance(flight["price"], int)
    assert isinstance(flight["seats_available"], int)


def test_airline_comes_from_the_normalized_airlines_table(client):
    flight = client.get("/flights/1").json()
    assert flight["airline"] == "Air India"
    assert flight["airline_code"] == "AI"


def test_search_flights_by_route(client):
    response = client.get("/flights", params={"origin": "BLR", "destination": "DEL"})
    assert response.status_code == 200
    flights = response.json()
    assert flights, "expected at least one BLR -> DEL flight in the seed data"
    assert all(f["origin"] == "BLR" and f["destination"] == "DEL" for f in flights)
    assert {"AI101", "6E202"} <= {f["flight_number"] for f in flights}
    departures = [f["departure_time"] for f in flights]
    assert departures == sorted(departures)


def test_route_search_is_case_insensitive(client):
    upper = client.get("/flights", params={"origin": "BLR", "destination": "DEL"}).json()
    lower = client.get("/flights", params={"origin": "blr", "destination": "del"}).json()
    assert upper == lower


def test_search_flights_by_date(client):
    response = client.get("/flights", params={"date": "2026-06-10"})
    assert response.status_code == 200
    flights = response.json()
    assert {f["flight_number"] for f in flights} == {"AI101", "6E202"}
    assert all(f["departure_time"].startswith("2026-06-10") for f in flights)


def test_search_with_no_matches_returns_an_empty_list(client):
    response = client.get("/flights", params={"origin": "BLR", "destination": "BLR"})
    assert response.status_code == 200
    assert response.json() == []


def test_invalid_date_is_rejected_with_422(client):
    response = client.get("/flights", params={"date": "tomorrow"})
    assert response.status_code == 422


def test_get_flight_by_id(client):
    response = client.get("/flights/1")
    assert response.status_code == 200
    flight = response.json()
    assert flight["id"] == 1
    assert flight["flight_number"] == "AI101"


def test_get_flight_invalid_id_returns_404(client):
    response = client.get("/flights/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Flight not found"}


@pytest.mark.parametrize("flight_id", [0, -1, 2**63, 99999999999999999999])
def test_ids_outside_the_valid_range_return_404_not_a_server_error(client, flight_id):
    assert client.get(f"/flights/{flight_id}").status_code == 404


def test_starting_the_app_again_does_not_duplicate_the_seed_data(client):
    # A second start-up (a restart, or another Cloud Run instance) must leave exactly the same rows.
    with TestClient(app) as second_instance:
        flights = second_instance.get("/flights").json()
    assert len(flights) == 5
    assert client.get("/flights/1").json()["flight_number"] == "AI101"
