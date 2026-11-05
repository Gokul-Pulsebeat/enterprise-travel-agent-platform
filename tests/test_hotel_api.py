"""Baseline tests for the hotel REST API (SQLite-backed, Step-0 behavior)."""

import pytest
from fastapi.testclient import TestClient

from hotel_api.app import app


@pytest.fixture(scope="module")
def client():
    # Using TestClient as a context manager runs the app's startup event,
    # which creates and seeds hotels.db if it does not exist yet.
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_hotels(client):
    response = client.get("/hotels")
    assert response.status_code == 200
    hotels = response.json()
    assert isinstance(hotels, list)
    assert len(hotels) >= 5
    expected_keys = {
        "id",
        "name",
        "city",
        "area",
        "check_in_date",
        "check_out_date",
        "price_per_night",
        "rooms_available",
        "rating",
    }
    assert expected_keys <= set(hotels[0])


def test_search_hotels_by_city(client):
    response = client.get("/hotels", params={"city": "Delhi"})
    assert response.status_code == 200
    hotels = response.json()
    assert hotels, "expected at least one Delhi hotel in the seed data"
    assert all(h["city"] == "Delhi" for h in hotels)
    assert {"Delhi Stay", "Budget Inn Delhi"} <= {h["name"] for h in hotels}
    # Results are ordered by nightly price, cheapest first.
    prices = [h["price_per_night"] for h in hotels]
    assert prices == sorted(prices)


def test_get_hotel_by_id(client):
    response = client.get("/hotels/1")
    assert response.status_code == 200
    hotel = response.json()
    assert hotel["id"] == 1
    assert hotel["name"] == "Delhi Stay"


def test_get_hotel_invalid_id_returns_404(client):
    response = client.get("/hotels/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Hotel not found"}
