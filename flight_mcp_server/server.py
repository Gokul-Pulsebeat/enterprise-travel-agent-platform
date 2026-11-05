# Import `os` so configuration can be read from environment variables.
import os

# Import `Optional` so tool arguments can be typed as present or missing.
from typing import Optional

# Import `requests` so this MCP server can call the normal flight REST API over HTTP.
import requests

# Import specific request exceptions so local-server failures can show friendly messages.
from requests import ConnectionError as RequestsConnectionError

# Import MCPServer (the MCP 2.x successor to FastMCP), a small helper that makes defining MCP tools simple.
from mcp.server.mcpserver import MCPServer


# Read the flight API base URL from the environment, defaulting to the local API server.
FLIGHT_API_BASE_URL = os.getenv("FLIGHT_API_BASE_URL", "http://127.0.0.1:8000")

# Create an MCP server named `flight-mcp-server`.
mcp = MCPServer("flight-mcp-server")


# Register the following Python function as an MCP tool.
@mcp.tool()
# Define an MCP tool that searches flights by origin and destination.
def search_flights(origin: str, destination: str, date: Optional[str] = None) -> list[dict]:
    # Document what this tool does so MCP clients and LLMs can understand it.
    """Search flights by origin, destination, and optional departure date."""
    # Build query parameters for the flight API.
    params = {"origin": origin, "destination": destination}
    # Check whether the caller supplied a departure date.
    if date:
        # Add the optional departure date filter to the query parameters.
        params["date"] = date
    # Start a block that can catch local flight API connection failures.
    try:
        # Call the normal REST API's `GET /flights` endpoint.
        response = requests.get(
            # Build the full URL to the flight search endpoint.
            f"{FLIGHT_API_BASE_URL}/flights",
            # Pass origin, destination, and optional date as HTTP query parameters.
            params=params,
            # Fail the HTTP request if it takes longer than 10 seconds.
            timeout=10,
        )
    # Catch the common case where `uvicorn flight_api.app:app --port 8000` is not running.
    except RequestsConnectionError as exc:
        # Raise a clear error that will be returned through the MCP call.
        raise RuntimeError(
            f"Could not connect to the flight API at {FLIGHT_API_BASE_URL}. "
            "Start it with: uvicorn flight_api.app:app --reload --port 8000"
        ) from exc
    # Raise an exception if the flight API returned a 4xx or 5xx error.
    response.raise_for_status()
    # Return the decoded JSON response back through MCP.
    return response.json()


# Register the following Python function as another MCP tool.
@mcp.tool()
# Define an MCP tool that fetches one flight by ID.
def get_flight(flight_id: int) -> dict:
    # Document what this tool does so MCP clients and LLMs can understand it.
    """Get one flight by its numeric ID."""
    # Start a block that can catch local flight API connection failures.
    try:
        # Call the normal REST API's `GET /flights/{flight_id}` endpoint.
        response = requests.get(f"{FLIGHT_API_BASE_URL}/flights/{flight_id}", timeout=10)
    # Catch the common case where `uvicorn flight_api.app:app --port 8000` is not running.
    except RequestsConnectionError as exc:
        # Raise a clear error that will be returned through the MCP call.
        raise RuntimeError(
            f"Could not connect to the flight API at {FLIGHT_API_BASE_URL}. "
            "Start it with: uvicorn flight_api.app:app --reload --port 8000"
        ) from exc
    # Raise an exception if the flight API returned a 4xx or 5xx error.
    response.raise_for_status()
    # Return the decoded JSON response back through MCP.
    return response.json()


# Check whether this file is being run directly rather than imported.
if __name__ == "__main__":
    # Start the MCP server using stdio so an MCP client can talk to it as a subprocess.
    mcp.run(transport="stdio")
