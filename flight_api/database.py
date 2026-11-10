# Import `Path` so we can build a database file path relative to this Python file.
from pathlib import Path

# Import Python's built-in SQLite library for the local mock database.
import sqlite3


# Build the path `flight_api/flights.db` beside this `database.py` file.
DB_PATH = Path(__file__).with_name("flights.db")


# Define simple mock flight rows that will be inserted into SQLite on first startup.
MOCK_FLIGHTS = [
    # Mock flight 1: flight number, airline, origin, destination, departure, arrival, price, seats.
    ("AI101", "Air India", "BLR", "DEL", "2026-06-10T08:30:00", "2026-06-10T11:10:00", 6800, 12),
    # Mock flight 2: another Bengaluru to Delhi option for search results.
    ("6E202", "IndiGo", "BLR", "DEL", "2026-06-10T13:15:00", "2026-06-10T15:55:00", 6200, 22),
    # Mock flight 3: Bengaluru to Mumbai option to make the dataset less one-route-only.
    ("UK303", "Vistara", "BLR", "BOM", "2026-06-11T09:00:00", "2026-06-11T10:45:00", 5400, 8),
    # Mock flight 4: Delhi to Bengaluru option for reverse-route testing.
    ("SG404", "SpiceJet", "DEL", "BLR", "2026-06-12T18:20:00", "2026-06-12T21:00:00", 5900, 15),
    # Mock flight 5: Chennai to Delhi option for another route.
    ("AI505", "Air India", "MAA", "DEL", "2026-06-13T07:40:00", "2026-06-13T10:35:00", 7100, 6),
]


# Define a helper function that opens a SQLite connection.
def get_connection() -> sqlite3.Connection:
    # Connect to the local SQLite database file.
    connection = sqlite3.connect(DB_PATH)
    # Make query results behave like dictionaries keyed by column name.
    connection.row_factory = sqlite3.Row
    # Return the configured database connection to the caller.
    return connection


# Define a helper function that creates and seeds the database.
def init_db() -> None:
    # Open a database connection and automatically close/commit it when the block ends.
    with get_connection() as connection:
        # Create the `flights` table if it does not already exist.
        connection.execute(
            # This SQL statement defines the columns for the mock flight table.
            """
            CREATE TABLE IF NOT EXISTS flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flight_number TEXT NOT NULL,
                airline TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                departure_time TEXT NOT NULL,
                arrival_time TEXT NOT NULL,
                price INTEGER NOT NULL,
                seats_available INTEGER NOT NULL
            )
            """
        )

        # Count how many rows already exist so we do not insert duplicate mock data.
        count = connection.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
        # Seed the table only when it is empty.
        if count == 0:
            # Insert every tuple from `MOCK_FLIGHTS` into the `flights` table.
            connection.executemany(
                # This SQL statement inserts one flight row using placeholder values.
                """
                INSERT INTO flights (
                    flight_number,
                    airline,
                    origin,
                    destination,
                    departure_time,
                    arrival_time,
                    price,
                    seats_available
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                # Provide the mock flight tuples as the values for the SQL placeholders.
                MOCK_FLIGHTS,
            )


# Define a helper function that converts a SQLite row into a normal Python dictionary.
def row_to_dict(row: sqlite3.Row) -> dict:
    # Convert the row object into `{column_name: value}` form for JSON responses.
    return dict(row)
