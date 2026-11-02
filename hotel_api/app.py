# Import `Optional` so query parameters can be typed as either a string or missing.
from typing import Optional

# Import FastAPI to create the web app, HTTPException for errors, and Query for query params.
from fastapi import FastAPI, HTTPException, Query

# Import database helpers from our local hotel-service database module.
from hotel_api.database import get_connection, init_db, row_to_dict


# Create the FastAPI application object that Uvicorn will serve.
app = FastAPI(title="Hotel Search API", version="1.0.0")


# Register this function to run when the FastAPI app starts.
@app.on_event("startup")
# Define the startup function that prepares the local hotel database.
def startup() -> None:
    # Create the SQLite table and seed mock data if needed.
    init_db()


# Register a public health-check endpoint at `GET /health`.
@app.get("/health")
# Define the health-check function.
def health() -> dict:
    # Return a tiny JSON object showing that the API process is alive.
    return {"status": "ok"}


# Register a public hotel-list/search endpoint at `GET /hotels`.
@app.get("/hotels")
# Define the function that handles hotel listing and optional city filtering.
def list_hotels(
    # Read the optional `city` query parameter, such as `?city=Delhi`.
    city: Optional[str] = Query(default=None, description="City name, for example Delhi"),
    # Read the optional `check_in_date` query parameter, such as `?check_in_date=2026-06-10`.
    check_in_date: Optional[str] = Query(default=None, description="Check-in date in YYYY-MM-DD format"),
# Tell FastAPI and readers that this endpoint returns a list of dictionaries.
) -> list[dict]:
    # Start with a query that returns all hotel rows.
    query = "SELECT * FROM hotels WHERE 1 = 1"
    # Create the list of SQL parameters that will safely fill the `?` placeholders.
    params: list[str] = []

    # Check whether the caller supplied a city filter.
    if city:
        # Add a case-insensitive city comparison to the SQL query.
        query += " AND UPPER(city) = UPPER(?)"
        # Add the user-provided city value as a SQL parameter.
        params.append(city)

    # Check whether the caller supplied a check-in date filter.
    if check_in_date:
        # Add an exact check-in date comparison to the SQL query.
        query += " AND check_in_date = ?"
        # Add the user-provided check-in date value as a SQL parameter.
        params.append(check_in_date)

    # Sort cheaper hotels first so the result is easy to scan.
    query += " ORDER BY price_per_night"

    # Open a database connection for the query.
    with get_connection() as connection:
        # Execute the query with parameters and fetch every matching row.
        rows = connection.execute(query, params).fetchall()

    # Convert SQLite rows into normal dictionaries so FastAPI can return JSON.
    return [row_to_dict(row) for row in rows]


# Register a public detail endpoint such as `GET /hotels/1`.
@app.get("/hotels/{hotel_id}")
# Define the function that fetches one hotel by its ID.
def get_hotel(hotel_id: int) -> dict:
    # Open a database connection for the lookup.
    with get_connection() as connection:
        # Query exactly one row by primary key.
        row = connection.execute("SELECT * FROM hotels WHERE id = ?", (hotel_id,)).fetchone()

    # Check whether SQLite found no matching row.
    if row is None:
        # Return an HTTP 404 error when the requested hotel ID does not exist.
        raise HTTPException(status_code=404, detail="Hotel not found")

    # Convert the SQLite row into a dictionary for the JSON response.
    return row_to_dict(row)
