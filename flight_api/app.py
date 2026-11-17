"""Flight REST API: async FastAPI on PostgreSQL (SQLAlchemy 2.0 Core + asyncpg)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date as date_type
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncConnection

from common.db import MAX_BIGINT, build_engine, check_ready, env_flag, get_connection, migrate_and_seed
from flight_api.database import MIGRATION_LOCK_KEY, flight_select, flights
from flight_api.seed import seed_mock_data

# One pooled connection per request, injected into the endpoints below.
DbConnection = Annotated[AsyncConnection, Depends(get_connection)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create the engine, migrate and seed the database, then serve; dispose the engine on shutdown.

    uvicorn finishes this start-up before it opens the listening socket, so a failed migration stops the
    process and the platform never routes traffic to a half-initialized instance.
    """
    engine = build_engine()
    try:
        await migrate_and_seed(
            engine,
            migrations_dir=Path(__file__).with_name("migrations"),
            lock_key=MIGRATION_LOCK_KEY,
            seed=seed_mock_data if env_flag("SEED_MOCK_DATA", default=True) else None,
        )
    except BaseException:
        await engine.dispose()
        raise
    app.state.engine = engine
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="Flight Search API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    """Liveness: the process is up. Deliberately does not touch the database."""
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness: the database answers a trivial query. Used by the CD health gate and Docker Compose."""
    if await check_ready(request.app.state.engine):
        return JSONResponse({"status": "ready"})
    return JSONResponse({"status": "unavailable"}, status_code=503)


@app.get("/flights")
async def list_flights(
    connection: DbConnection,
    origin: Optional[str] = Query(default=None, description="Origin airport code, for example BLR"),
    destination: Optional[str] = Query(default=None, description="Destination airport code, for example DEL"),
    date: Optional[date_type] = Query(default=None, description="Departure date, YYYY-MM-DD"),
) -> list[dict]:
    """Search flights, earliest departure first. Filters are optional and case-insensitive."""
    statement = flight_select().order_by(flights.c.departure_time, flights.c.id)

    if origin:
        statement = statement.where(flights.c.origin_code == origin.strip().upper())
    if destination:
        statement = statement.where(flights.c.destination_code == destination.strip().upper())
    if date:
        # A half-open range on the timestamp (instead of casting the column) keeps the index usable.
        day_start = datetime.combine(date, time.min)
        statement = statement.where(
            flights.c.departure_time >= day_start,
            flights.c.departure_time < day_start + timedelta(days=1),
        )

    result = await connection.execute(statement)
    return [dict(row) for row in result.mappings()]


@app.get("/flights/{flight_id}")
async def get_flight(flight_id: int, connection: DbConnection) -> dict:
    """Return one flight by ID, or 404 if it does not exist."""
    # IDs outside BIGINT's range cannot exist; answering 404 here avoids a database error.
    if flight_id < 1 or flight_id > MAX_BIGINT:
        raise HTTPException(status_code=404, detail="Flight not found")

    result = await connection.execute(flight_select().where(flights.c.id == flight_id))
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return dict(row)
