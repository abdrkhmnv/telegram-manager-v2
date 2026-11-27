"""Alembic muhiti (asinxron, asyncpg).

Ulanish manzili ``DATABASE_URL`` dan olinadi (``app.config.DatabaseSettings``).
Dasturiy chaqiruvlarda tayyor ulanishni ``config.attributes["connection"]``
orqali uzatish mumkin.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import database.models  # noqa: F401  — barcha jadvallarni metadata'ga ro'yxatdan o'tkazadi
from app.config import DatabaseSettings
from database.base import Base

config = context.config

if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return DatabaseSettings().database_url.get_secret_value()  # type: ignore[call-arg]


def _configure(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=False,
        **kwargs,  # type: ignore[arg-type]
    )


def run_migrations_offline() -> None:
    """``alembic upgrade head --sql`` — SQL skriptni bazaga ulanmasdan chiqaradi."""
    _configure(url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_database_url(), poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_sync(connection)
    else:
        asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
