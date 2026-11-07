"""Baseline tests for the prompt-driven agent running in mock (no-LLM) mode."""

import json

from agent.agent import (
    build_mcp_server_env,
    extract_airport_codes,
    extract_date,
    infer_route,
    plan_with_mock,
    resolve_arguments,
)


# ---------------------------------------------------------------------------
# extract_airport_codes
# ---------------------------------------------------------------------------
def test_extract_airport_codes_finds_known_codes_in_order():
    assert extract_airport_codes("Fly from BLR to DEL please") == ["BLR", "DEL"]


def test_extract_airport_codes_is_case_insensitive():
    assert extract_airport_codes("fly from blr to bom") == ["BLR", "BOM"]


def test_extract_airport_codes_ignores_unknown_codes():
    # XYZ is three capital letters but not in KNOWN_AIRPORT_CODES.
    assert extract_airport_codes("XYZ to DEL") == ["DEL"]


def test_extract_airport_codes_returns_empty_when_none_present():
    assert extract_airport_codes("hello there") == []


# ---------------------------------------------------------------------------
# extract_date
# ---------------------------------------------------------------------------
def test_extract_date_returns_first_iso_date():
    assert extract_date("Leaving on 2026-06-10, back 2026-06-15") == "2026-06-10"


def test_extract_date_returns_none_without_a_date():
    assert extract_date("sometime next week") is None


# ---------------------------------------------------------------------------
# infer_route
# ---------------------------------------------------------------------------
def test_infer_route_from_airport_codes():
    assert infer_route("BLR to DEL") == ("BLR", "DEL")


def test_infer_route_from_city_names():
    assert infer_route("Help me travel from Bangalore to Delhi") == ("BLR", "DEL")


def test_infer_route_returns_none_when_no_route_found():
    assert infer_route("hello there") is None


# ---------------------------------------------------------------------------
# plan_with_mock
# ---------------------------------------------------------------------------
def test_plan_with_mock_parallel_flight_and_hotel():
    plan = plan_with_mock("Help me travel from Bangalore to Delhi on 2026-06-10 and stay there.")
    steps = {step["step_id"]: step for step in plan["steps"]}

    assert set(steps) == {"search_flights", "search_hotels"}

    flight = steps["search_flights"]
    assert flight["server_name"] == "flight"
    assert flight["tool_name"] == "search_flights"
    assert flight["arguments"] == {"origin": "BLR", "destination": "DEL", "date": "2026-06-10"}
    assert flight["depends_on"] == []

    hotel = steps["search_hotels"]
    assert hotel["server_name"] == "hotel"
    assert hotel["tool_name"] == "search_hotels"
    assert hotel["arguments"] == {"city": "Delhi", "check_in_date": "2026-06-10"}
    # The date is known up front, so both steps can run in parallel.
    assert hotel["depends_on"] == []


def test_plan_with_mock_sequential_hotel_depends_on_flight_date():
    plan = plan_with_mock("Find a flight from Bangalore to Delhi and then find hotels based on when I arrive.")
    steps = {step["step_id"]: step for step in plan["steps"]}

    assert set(steps) == {"search_flights", "search_hotels"}
    assert steps["search_flights"]["arguments"] == {"origin": "BLR", "destination": "DEL"}
    assert steps["search_flights"]["depends_on"] == []

    hotel = steps["search_hotels"]
    assert hotel["arguments"] == {"city": "Delhi", "check_in_date": "$first_flight_date:search_flights"}
    assert hotel["depends_on"] == ["search_flights"]


def test_plan_with_mock_tools_prompt_returns_local_list_tools_step():
    plan = plan_with_mock("What travel tools can you use?")
    assert [step["tool_name"] for step in plan["steps"]] == ["list_tools"]
    assert plan["steps"][0]["server_name"] == "local"


def test_plan_with_mock_without_route_or_city_returns_final_answer():
    plan = plan_with_mock("hello there")
    assert plan["steps"] == []
    assert "route or city" in plan["final_answer"]


def test_resolve_arguments_replaces_first_flight_date_placeholder():
    completed = {
        "search_flights": {
            "raw_text": json.dumps([{"departure_time": "2026-06-10T08:30:00"}]),
        }
    }
    resolved = resolve_arguments(
        {"city": "Delhi", "check_in_date": "$first_flight_date:search_flights"},
        completed,
    )
    assert resolved == {"city": "Delhi", "check_in_date": "2026-06-10"}


# ---------------------------------------------------------------------------
# build_mcp_server_env
# ---------------------------------------------------------------------------
def test_build_mcp_server_env_forwards_api_base_urls(monkeypatch):
    monkeypatch.setenv("FLIGHT_API_BASE_URL", "http://flight_api:8000")
    monkeypatch.setenv("HOTEL_API_BASE_URL", "http://hotel_api:8001")
    assert build_mcp_server_env() == {
        "FLIGHT_API_BASE_URL": "http://flight_api:8000",
        "HOTEL_API_BASE_URL": "http://hotel_api:8001",
    }


def test_build_mcp_server_env_omits_unset_variables(monkeypatch):
    monkeypatch.delenv("FLIGHT_API_BASE_URL", raising=False)
    monkeypatch.delenv("HOTEL_API_BASE_URL", raising=False)
    assert build_mcp_server_env() == {}
