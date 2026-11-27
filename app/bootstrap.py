"""Ilovani yig'ish: sozlamalar -> log -> komponentlar -> lifecycle.

1-bosqichda faqat ma'lumotlar bazasi komponenti mavjud. 2-bosqichda
Telethon userbot va Control Bot shu ro'yxatga qo'shiladi.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.config import AppSettings, DatabaseSettings
from app.lifecycle import Component, LifecycleManager, install_signal_handlers
from core.exceptions import MigrationOutOfDateError
from database.connection import Database
from database.migration_check import MigrationStatus, get_migration_status
from utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


class DatabaseComponent:
    """PostgreSQL'ga ulanadi va sxema oxirgi migratsiyada ekanini tekshiradi."""

    name = "database"

    def __init__(self, database: Database, *, connect_attempts: int = 10) -> None:
        self._database = database
        self._connect_attempts = connect_attempts

    async def start(self) -> None:
        await self._database.wait_until_ready(attempts=self._connect_attempts)
        status = await get_migration_status(self._database)
        ensure_migrations_current(status)

    async def stop(self) -> None:
        await self._database.dispose()


def ensure_migrations_current(status: MigrationStatus) -> None:
    if not status.is_current:
        current = ", ".join(sorted(status.current)) or "yo'q"
        heads = ", ".join(sorted(status.heads)) or "yo'q"
        raise MigrationOutOfDateError(
            f"Ma'lumotlar bazasi sxemasi eskirgan (joriy: {current}, kerak: {heads}). "
            "Avval bajaring: alembic upgrade head"
        )


@dataclass(slots=True)
class Application:
    settings: AppSettings
    database: Database
    lifecycle: LifecycleManager


def configure_logging(settings: AppSettings) -> None:
    setup_logging(settings.log_level, settings.log_format.value, settings.log_dir)


def ensure_storage_dirs(settings: AppSettings) -> None:
    """Saqlash katalogini faqat egasi o'qiy oladigan ruxsat bilan yaratadi."""
    settings.storage_dir.mkdir(mode=0o700, parents=True, exist_ok=True)


def build_application(app_settings: AppSettings, db_settings: DatabaseSettings) -> Application:
    database = Database(db_settings)
    components: list[Component] = [DatabaseComponent(database)]
    return Application(
        settings=app_settings,
        database=database,
        lifecycle=LifecycleManager(components),
    )


async def run_application(application: Application) -> None:
    shutdown = asyncio.Event()
    install_signal_handlers(shutdown)
    logger.info(
        "Telegram Manager v2 ishga tushmoqda",
        extra={"env": application.settings.app_env.value},
    )
    await application.lifecycle.run_until(shutdown)
    logger.info("Telegram Manager v2 to'xtatildi")
