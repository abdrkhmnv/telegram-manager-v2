"""Asinxron PostgreSQL ulanishi, sessiyalar va startup tekshiruvlari."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import DatabaseSettings
from core.exceptions import DatabaseUnavailableError
from utils.logger import get_logger, register_secret

logger = get_logger(__name__)

APPLICATION_NAME = "telegram-manager-v2"


def build_engine(settings: DatabaseSettings) -> AsyncEngine:
    url = settings.database_url.get_secret_value()
    register_secret(make_url(url).password)
    return create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=settings.db_echo,
        connect_args={
            "timeout": settings.db_connect_timeout,
            "command_timeout": settings.db_command_timeout,
            "server_settings": {"application_name": APPLICATION_NAME, "timezone": "UTC"},
        },
    )


class Database:
    """Engine va sessiya fabrikasini o'rab turuvchi obyekt.

    ``session()`` — bitta tranzaksiya (unit of work): blok muvaffaqiyatli
    tugasa ``commit``, istisno bo'lsa ``rollback``.
    """

    def __init__(self, settings: DatabaseSettings) -> None:
        self._engine = build_engine(settings)
        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, autoflush=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def ping(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def wait_until_ready(
        self, attempts: int = 5, base_delay: float = 1.0, max_delay: float = 15.0
    ) -> None:
        """Bazaga ulanishni eksponensial kutish (backoff) bilan bir necha bor sinaydi."""
        if attempts < 1:
            raise ValueError("attempts kamida 1 bo'lishi kerak")
        delay = base_delay
        for attempt in range(1, attempts + 1):
            try:
                await self.ping()
            except (OSError, SQLAlchemyError, TimeoutError) as exc:
                if attempt == attempts:
                    raise DatabaseUnavailableError(
                        f"PostgreSQL'ga ulanib bo'lmadi ({attempts} urinish): {type(exc).__name__}"
                    ) from exc
                logger.warning(
                    "PostgreSQL hali tayyor emas, qayta urinish",
                    extra={"attempt": attempt, "retry_in": delay, "error": type(exc).__name__},
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
            else:
                logger.info("PostgreSQL ulanishi tayyor", extra={"attempt": attempt})
                return

    async def dispose(self) -> None:
        await self._engine.dispose()
