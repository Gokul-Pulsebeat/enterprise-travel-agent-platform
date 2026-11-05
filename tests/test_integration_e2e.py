"""End-to-end tests: agent -> MCP client -> MCP server (stdio) -> REST API -> SQLite.

These start real uvicorn processes for flight_api (8000) and hotel_api (8001), because the
MCP servers call the APIs over HTTP and TestClient cannot serve real network requests.
Ports are fixed: the MCP servers are spawned by the MCP client with a restricted
environment, so they always use the default API base URLs.

Deselect with:  pytest -m "not integration"
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from agent import agent as agent_module

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[1]

API_SERVICES = {
    "flight_api": 8000,
    "hotel_api": 8001,
}


def _is_up(port: int) -> bool:
    try:
        return requests.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200
    except requests.RequestException:
        return False


def _wait_until_up(port: int, process: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_up(port):
            return
        if process.poll() is not None:
            raise RuntimeError(f"API process on port {port} exited early with code {process.returncode}")
        time.sleep(0.25)
    raise RuntimeError(f"API on port {port} did not become healthy within {timeout} seconds")


@pytest.fixture(scope="module")
def running_apis():
    """Ensure both REST APIs are reachable; start (and later stop) any that are not already running."""
    started: list[subprocess.Popen] = []
    try:
        for package, port in API_SERVICES.items():
            if _is_up(port):
                continue  # Reuse an API the developer already started.
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", f"{package}.app:app", "--port", str(port)],
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            started.append(process)
            _wait_until_up(port, process)
        yield
    finally:
        for process in started:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


@pytest.fixture
def mock_mode(monkeypatch):
    # LLM_PROVIDER is read once at import time, so patch the module attribute too.
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setattr(agent_module, "LLM_PROVIDER", "mock")


def _run(prompt: str) -> str:
    async def _go() -> str:
        # The timeout keeps a broken handshake or hung subprocess from stalling the run.
        return await asyncio.wait_for(agent_module.run_agent(prompt), timeout=90)

    return asyncio.run(_go())


def test_e2e_lists_tools_from_both_mcp_servers(mock_mode):
    # Handshake-level check: spawns both MCP servers over stdio and lists their tools.
    # Does not need the REST APIs, because the "tools" prompt returns before any tool call.
    result = _run("What travel tools can you use?")

    assert result.startswith("Available MCP tools:")
    for tool_label in (
        "flight.search_flights",
        "flight.get_flight",
        "hotel.search_hotels",
        "hotel.get_hotel",
    ):
        assert tool_label in result


def test_e2e_parallel_flight_and_hotel_search(running_apis, mock_mode):
    result = _run("Help me travel from Bangalore to Delhi on 2026-06-10 and stay there.")

    # Flight leg: reached flight_mcp_server -> flight_api -> flights.db
    assert "Flights:" in result
    assert "AI101" in result
    assert "6E202" in result

    # Hotel leg: reached hotel_mcp_server -> hotel_api -> hotels.db
    assert "Hotels:" in result
    assert "Delhi Stay" in result
    assert "Budget Inn Delhi" in result


def test_e2e_sequential_hotel_uses_first_flight_date(running_apis, mock_mode):
    result = _run("Find a flight from Bangalore to Delhi and then find hotels based on when I arrive.")

    assert "Flights:" in result
    assert "AI101" in result

    # If $first_flight_date had not been resolved to 2026-06-10, the hotel search would have been
    # sent a literal placeholder string and returned "No matching hotels."
    assert "No matching hotels" not in result
    assert "Delhi Stay" in result
