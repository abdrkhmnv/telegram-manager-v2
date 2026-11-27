"""Integratsion testlar uchun haqiqiy PostgreSQL.

``TEST_DATABASE_URL`` berilmasa, bu katalogdagi testlar o'tkazib yuboriladi.
Sxema oldindan ``alembic upgrade head`` bilan yaratilgan bo'lishi kerak
(CI shunday qiladi). Har bir testdan oldin barcha jadvallar tozalanadi.

DIQQAT: TEST_DATABASE_URL ga hech qachon ishlab chiqarish bazasini ko'rsatmang.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
            if not TEST_DATABASE_URL:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL o'rnatilmagan"))


if TEST_DATABASE_URL:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import DatabaseSettings
    from database.base import Base
    from database.connection import Database

    @pytest.fixture
    async def database() -> AsyncIterator[Database]:
        settings = DatabaseSettings(_env_file=None, database_url=TEST_DATABASE_URL)
        db = Database(settings)
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        async with db.engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        try:
            yield db
        finally:
            await db.dispose()

    @pytest.fixture
    async def session(database: Database) -> AsyncIterator[AsyncSession]:
        async with database.session() as db_session:
            yield db_session
