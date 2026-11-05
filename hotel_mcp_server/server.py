# Import `os` so configuration can be read from environment variables.
import os

# Import `Optional` so tool arguments can be typed as present or missing.
from typing import Optional

# Import `requests` so this MCP server can call the normal hotel REST API over HTTP.
import requests

# Import specific request exceptions so local-server failures can show friendly messages.
from requests import ConnectionError as RequestsConnectionError

# Import MCPServer (the MCP 2.x successor to FastMCP), a small helper that makes defining MCP tools simple.
from mcp.server.mcpserver import MCPServer


# Read the hotel API base URL from the environment, defaulting to the local hotel API server.
HOTEL_API_BASE_URL = os.getenv("HOTEL_API_BASE_URL", "http://127.0.0.1:8001")

# Create an MCP server named `hotel-mcp-server`.
mcp = MCPServer("hotel-mcp-server")


# Register the following Python function as an MCP tool.
@mcp.tool()
# Define an MCP tool that searches hotels by city.
def search_hotels(city: str, check_in_date: Optional[str] = None) -> list[dict]:
    # Document what this tool does so MCP clients and LLMs can understand it.
    """Search hotels by city name and optional check-in date."""
    # Build query parameters for the hotel API.
    params = {"city": city}
    # Check whether the caller supplied a check-in date.
    if check_in_date:
        # Add the optional check-in date filter to the query parameters.
        params["check_in_date"] = check_in_date
    # Start a block that can catch local hotel API connection failures.
    try:
        # Call the normal REST API's `GET /hotels` endpoint.
        response = requests.get(
            # Build the full URL to the hotel search endpoint.
            f"{HOTEL_API_BASE_URL}/hotels",
            # Pass city and optional check-in date as HTTP query parameters.
            params=params,
            # Fail the HTTP request if it takes longer than 10 seconds.
            timeout=10,
        )
    # Catch the common case where `uvicorn hotel_api.app:app --port 8001` is not running.
    except RequestsConnectionError as exc:
        # Raise a clear error that will be returned through the MCP call.
        raise RuntimeError(
            f"Could not connect to the hotel API at {HOTEL_API_BASE_URL}. "
            "Start it with: uvicorn hotel_api.app:app --reload --port 8001"
        ) from exc

    # Raise an exception if the hotel API returned a 4xx or 5xx error.
    response.raise_for_status()
    # Return the decoded JSON response back through MCP.
    return response.json()


# Register the following Python function as another MCP tool.
@mcp.tool()
# Define an MCP tool that fetches one hotel by ID.
def get_hotel(hotel_id: int) -> dict:
    # Document what this tool does so MCP clients and LLMs can understand it.
    """Get one hotel by its numeric ID."""
    # Start a block that can catch local hotel API connection failures.
    try:
        # Call the normal REST API's `GET /hotels/{hotel_id}` endpoint.
        response = requests.get(f"{HOTEL_API_BASE_URL}/hotels/{hotel_id}", timeout=10)
    # Catch the common case where `uvicorn hotel_api.app:app --port 8001` is not running.
    except RequestsConnectionError as exc:
        # Raise a clear error that will be returned through the MCP call.
        raise RuntimeError(
            f"Could not connect to the hotel API at {HOTEL_API_BASE_URL}. "
            "Start it with: uvicorn hotel_api.app:app --reload --port 8001"
        ) from exc

    # Raise an exception if the hotel API returned a 4xx or 5xx error.
    response.raise_for_status()
    # Return the decoded JSON response back through MCP.
    return response.json()


# Check whether this file is being run directly rather than imported.
if __name__ == "__main__":
    # Start the MCP server using stdio so an MCP client can talk to it as a subprocess.
    mcp.run(transport="stdio")
