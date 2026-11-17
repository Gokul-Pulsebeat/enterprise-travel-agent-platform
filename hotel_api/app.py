"""Hotel REST API: async FastAPI on PostgreSQL (SQLAlchemy 2.0 Core + asyncpg)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date as date_type
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncConnection

from common.db import MAX_BIGINT, build_engine, check_ready, env_flag, get_connection, migrate_and_seed
from hotel_api.database import MIGRATION_LOCK_KEY, hotel_offers, hotels, offer_select
from hotel_api.seed import seed_mock_data

# One pooled connection per request, injected into the endpoints below.
DbConnection = Annotated[AsyncConnection, Depends(get_connection)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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


app = FastAPI(title="Hotel Search API", version="1.0.0", lifespan=lifespan)


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


@app.get("/hotels")
async def list_hotels(
    connection: DbConnection,
    city: Optional[str] = Query(default=None, description="City name, for example Delhi"),
    check_in_date: Optional[date_type] = Query(default=None, description="Check-in date, YYYY-MM-DD"),
) -> list[dict]:
    """Search hotel offers, cheapest first. Filters are optional; the city match is case-insensitive."""
    statement = offer_select().order_by(hotel_offers.c.price_per_night, hotel_offers.c.id)

    if city:
        statement = statement.where(func.upper(hotels.c.city) == city.strip().upper())
    if check_in_date:
        statement = statement.where(hotel_offers.c.check_in_date == check_in_date)

    result = await connection.execute(statement)
    return [dict(row) for row in result.mappings()]


@app.get("/hotels/{hotel_id}")
async def get_hotel(hotel_id: int, connection: DbConnection) -> dict:
    """Return one hotel offer by ID, or 404 if it does not exist."""
    # IDs outside BIGINT's range cannot exist; answering 404 here avoids a database error.
    if hotel_id < 1 or hotel_id > MAX_BIGINT:
        raise HTTPException(status_code=404, detail="Hotel not found")

    result = await connection.execute(offer_select().where(hotel_offers.c.id == hotel_id))
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Hotel not found")
    return dict(row)
