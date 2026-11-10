# Import `Optional` so query parameters can be typed as either a string or missing.
from typing import Optional

# Import FastAPI to create the web app, HTTPException for errors, and Query for query params.
from fastapi import FastAPI, HTTPException, Query

# Import database helpers from our local business-service database module.
from flight_api.database import get_connection, init_db, row_to_dict


# Create the FastAPI application object that Uvicorn will serve.
app = FastAPI(title="Flight Search API", version="1.0.0")


# Register this function to run when the FastAPI app starts.
@app.on_event("startup")
# Define the startup function that prepares the local database.
def startup() -> None:
    # Create the SQLite table and seed mock data if needed.
    init_db()


# Register a public health-check endpoint at `GET /health`.
@app.get("/health")
# Define the health-check function.
def health() -> dict:
    # Return a tiny JSON object showing that the API process is alive.
    return {"status": "ok"}


# Register a public flight-list/search endpoint at `GET /flights`.
@app.get("/flights")
# Define the function that handles flight listing and optional filtering.
def list_flights(
    # Read the optional `origin` query parameter, such as `?origin=BLR`.
    origin: Optional[str] = Query(default=None, description="Airport code, for example BLR"),
    # Read the optional `destination` query parameter, such as `?destination=DEL`.
    destination: Optional[str] = Query(default=None, description="Airport code, for example DEL"),
    # Read the optional `date` query parameter, such as `?date=2026-06-10`.
    date: Optional[str] = Query(default=None, description="Departure date in YYYY-MM-DD format"),
    # Tell FastAPI and readers that this endpoint returns a list of dictionaries.
) -> list[dict]:
    # Start with a query that returns all rows; `1 = 1` makes later `AND` clauses easy to append.
    query = "SELECT * FROM flights WHERE 1 = 1"
    # Create the list of SQL parameters that will safely fill the `?` placeholders.
    params: list[str] = []

    # Check whether the caller supplied an origin filter.
    if origin:
        # Add a case-insensitive origin comparison to the SQL query.
        query += " AND UPPER(origin) = UPPER(?)"
        # Add the user-provided origin value as a SQL parameter.
        params.append(origin)

    # Check whether the caller supplied a destination filter.
    if destination:
        # Add a case-insensitive destination comparison to the SQL query.
        query += " AND UPPER(destination) = UPPER(?)"
        # Add the user-provided destination value as a SQL parameter.
        params.append(destination)

    # Check whether the caller supplied a departure date filter.
    if date:
        # Match the first 10 characters of the ISO departure timestamp, which is YYYY-MM-DD.
        query += " AND substr(departure_time, 1, 10) = ?"
        # Add the user-provided date value as a SQL parameter.
        params.append(date)

    # Sort results by departure time so earlier flights appear first.
    query += " ORDER BY departure_time"

    # Open a database connection for the query.
    with get_connection() as connection:
        # Execute the query with parameters and fetch every matching row.
        rows = connection.execute(query, params).fetchall()

    # Convert SQLite rows into normal dictionaries so FastAPI can return JSON.
    return [row_to_dict(row) for row in rows]


# Register a public detail endpoint such as `GET /flights/1`.
@app.get("/flights/{flight_id}")
# Define the function that fetches one flight by its ID.
def get_flight(flight_id: int) -> dict:
    # Open a database connection for the lookup.
    with get_connection() as connection:
        # Query exactly one row by primary key.
        row = connection.execute("SELECT * FROM flights WHERE id = ?", (flight_id,)).fetchone()

    # Check whether SQLite found no matching row.
    if row is None:
        # Return an HTTP 404 error when the requested flight ID does not exist.
        raise HTTPException(status_code=404, detail="Flight not found")

    # Convert the SQLite row into a dictionary for the JSON response.
    return row_to_dict(row)
