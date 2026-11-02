# Import `Path` so we can build a database file path relative to this Python file.
from pathlib import Path

# Import Python's built-in SQLite library for the local mock hotel database.
import sqlite3


# Build the path `hotel_api/hotels.db` beside this `database.py` file.
DB_PATH = Path(__file__).with_name("hotels.db")


# Define simple mock hotel rows that will be inserted into SQLite on first startup.
MOCK_HOTELS = [
    # Mock hotel 1: name, city, area, check-in date, check-out date, nightly price, rooms, rating.
    ("Delhi Stay", "Delhi", "Connaught Place", "2026-06-10", "2026-06-11", 4200, 5, 4.2),
    # Mock hotel 2: another Delhi option with a lower price.
    ("Budget Inn Delhi", "Delhi", "Karol Bagh", "2026-06-10", "2026-06-11", 2600, 12, 3.8),
    # Mock hotel 3: Mumbai option for cross-city testing.
    ("Sea View Mumbai", "Mumbai", "Marine Drive", "2026-06-11", "2026-06-12", 7800, 3, 4.6),
    # Mock hotel 4: Bengaluru option for local-city testing.
    ("Garden City Hotel", "Bengaluru", "Indiranagar", "2026-06-12", "2026-06-13", 5100, 7, 4.1),
    # Mock hotel 5: Chennai option for another simple route.
    ("Marina Comfort", "Chennai", "Mylapore", "2026-06-13", "2026-06-14", 3900, 9, 4.0),
]


# Define a helper function that opens a SQLite connection.
def get_connection() -> sqlite3.Connection:
    # Connect to the local SQLite database file.
    connection = sqlite3.connect(DB_PATH)
    # Make query results behave like dictionaries keyed by column name.
    connection.row_factory = sqlite3.Row
    # Return the configured database connection to the caller.
    return connection


# Define a helper function that creates and seeds the hotel database.
def init_db() -> None:
    # Open a database connection and automatically close/commit it when the block ends.
    with get_connection() as connection:
        # Create the `hotels` table if it does not already exist.
        connection.execute(
            # This SQL statement defines the columns for the mock hotel table.
            """
            CREATE TABLE IF NOT EXISTS hotels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                area TEXT NOT NULL,
                check_in_date TEXT NOT NULL,
                check_out_date TEXT NOT NULL,
                price_per_night INTEGER NOT NULL,
                rooms_available INTEGER NOT NULL,
                rating REAL NOT NULL
            )
            """
        )

        # Count how many rows already exist so we do not insert duplicate mock data.
        count = connection.execute("SELECT COUNT(*) FROM hotels").fetchone()[0]
        # Seed the table only when it is empty.
        if count == 0:
            # Insert every tuple from `MOCK_HOTELS` into the `hotels` table.
            connection.executemany(
                # This SQL statement inserts one hotel row using placeholder values.
                """
                INSERT INTO hotels (
                    name,
                    city,
                    area,
                    check_in_date,
                    check_out_date,
                    price_per_night,
                    rooms_available,
                    rating
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                # Provide the mock hotel tuples as the values for the SQL placeholders.
                MOCK_HOTELS,
            )


# Define a helper function that converts a SQLite row into a normal Python dictionary.
def row_to_dict(row: sqlite3.Row) -> dict:
    # Convert the row object into `{column_name: value}` form for JSON responses.
    return dict(row)

