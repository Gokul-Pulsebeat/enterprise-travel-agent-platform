"""Baseline tests for the flight REST API (SQLite-backed, Step-0 behavior)."""

import pytest
from fastapi.testclient import TestClient

from flight_api.app import app


@pytest.fixture(scope="module")
def client():
    # Using TestClient as a context manager runs the app's startup event,
    # which creates and seeds flights.db if it does not exist yet.
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_flights(client):
    response = client.get("/flights")
    assert response.status_code == 200
    flights = response.json()
    assert isinstance(flights, list)
    assert len(flights) >= 5
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


def test_search_flights_by_route(client):
    response = client.get("/flights", params={"origin": "BLR", "destination": "DEL"})
    assert response.status_code == 200
    flights = response.json()
    assert flights, "expected at least one BLR -> DEL flight in the seed data"
    assert all(f["origin"] == "BLR" and f["destination"] == "DEL" for f in flights)
    assert {"AI101", "6E202"} <= {f["flight_number"] for f in flights}
    # Results are ordered by departure time, earliest first.
    departures = [f["departure_time"] for f in flights]
    assert departures == sorted(departures)


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
