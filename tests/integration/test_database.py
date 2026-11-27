from __future__ import annotations

import pytest

from app.bootstrap import DatabaseComponent, ensure_migrations_current
from core.exceptions import MigrationOutOfDateError
from database.connection import Database
from database.migration_check import MigrationStatus, get_migration_status


async def test_ping_and_session_rollback(database: Database) -> None:
    from database.repositories import SettingsRepository

    await database.ping()
    with pytest.raises(RuntimeError):
        async with database.session() as session:
            await SettingsRepository(session).set("rollback.me", {"a": 1})
            raise RuntimeError("abort")
    async with database.session() as session:
        assert await SettingsRepository(session).get("rollback.me") is None


async def test_schema_is_at_head(database: Database) -> None:
    status = await get_migration_status(database)
    assert status.is_current, status
    ensure_migrations_current(status)


async def test_database_component_starts(database: Database) -> None:
    component = DatabaseComponent(database, connect_attempts=1)
    await component.start()


def test_outdated_schema_is_rejected() -> None:
    with pytest.raises(MigrationOutOfDateError, match="alembic upgrade head"):
        ensure_migrations_current(MigrationStatus(current=frozenset(), heads=frozenset({"0001"})))
