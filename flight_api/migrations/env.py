"""Alembic environment for flight_api. All logic is shared in common/alembic_env.py."""

from alembic import context

from common.alembic_env import run_migrations
from flight_api.database import SCHEMA, metadata

run_migrations(context, schema=SCHEMA, metadata=metadata)
