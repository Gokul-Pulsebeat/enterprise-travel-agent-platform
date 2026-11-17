"""Tests for the hotel REST API against a real PostgreSQL database (migrations and seed run in the lifespan)."""

import pytest
from fastapi.testclient import TestClient

from hotel_api.app import app

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


def test_list_hotels(client):
    response = client.get("/hotels")
    assert response.status_code == 200
    hotels = response.json()
    assert isinstance(hotels, list)
    assert len(hotels) == 5
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
    # Results are ordered by nightly price, cheapest first.
    prices = [h["price_per_night"] for h in hotels]
    assert prices == sorted(prices)


def test_hotels_keep_the_original_json_formats(client):
    hotel = client.get("/hotels/1").json()
    assert hotel["check_in_date"] == "2026-06-10"
    assert hotel["check_out_date"] == "2026-06-11"
    assert hotel["rating"] == 4.2
    assert isinstance(hotel["price_per_night"], int)


def test_results_join_the_property_and_its_offer(client):
    hotel = client.get("/hotels/1").json()
    # `id` is the bookable offer; `hotel_id` identifies the property it belongs to.
    assert hotel["id"] == 1
    assert hotel["hotel_id"] == 1
    assert hotel["name"] == "Delhi Stay"
    assert hotel["area"] == "Connaught Place"


def test_search_hotels_by_city(client):
    response = client.get("/hotels", params={"city": "Delhi"})
    assert response.status_code == 200
    hotels = response.json()
    assert hotels, "expected at least one Delhi hotel in the seed data"
    assert all(h["city"] == "Delhi" for h in hotels)
    assert {"Delhi Stay", "Budget Inn Delhi"} <= {h["name"] for h in hotels}
    prices = [h["price_per_night"] for h in hotels]
    assert prices == sorted(prices)


def test_city_search_is_case_insensitive(client):
    assert (
        client.get("/hotels", params={"city": "delhi"}).json() == client.get("/hotels", params={"city": "DELHI"}).json()
    )
    assert client.get("/hotels", params={"city": "delhi"}).json()


def test_search_hotels_by_check_in_date(client):
    response = client.get("/hotels", params={"city": "Delhi", "check_in_date": "2026-06-10"})
    assert response.status_code == 200
    assert {h["name"] for h in response.json()} == {"Delhi Stay", "Budget Inn Delhi"}

    other_day = client.get("/hotels", params={"city": "Delhi", "check_in_date": "2026-06-20"})
    assert other_day.json() == []


def test_invalid_check_in_date_is_rejected_with_422(client):
    response = client.get("/hotels", params={"check_in_date": "tomorrow"})
    assert response.status_code == 422


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


@pytest.mark.parametrize("hotel_id", [0, -1, 2**63, 99999999999999999999])
def test_ids_outside_the_valid_range_return_404_not_a_server_error(client, hotel_id):
    assert client.get(f"/hotels/{hotel_id}").status_code == 404


def test_starting_the_app_again_does_not_duplicate_the_seed_data(client):
    # A second start-up (a restart, or another Cloud Run instance) must leave exactly the same rows.
    with TestClient(app) as second_instance:
        hotels = second_instance.get("/hotels").json()
    assert len(hotels) == 5
    assert client.get("/hotels/1").json()["name"] == "Delhi Stay"
