"""Ilovani yig'ish: sozlamalar -> log -> komponentlar -> lifecycle.

Komponentlar tartibi: baza -> userbot -> Control Bot -> heartbeat.
To'xtatish teskari tartibda.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.config import AppSettings, DatabaseSettings, TelegramSettings
from app.health import HEALTH_FILENAME, HeartbeatComponent
from app.lifecycle import Component, LifecycleManager, install_signal_handlers
from bot.storage import PostgresStorage
from core.control_bot import ControlBotComponent
from core.exceptions import MigrationOutOfDateError
from core.userbot import UserbotComponent
from database.connection import Database
from database.migration_check import MigrationStatus, get_migration_status
from services.status_service import StatusService
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


def health_file(settings: AppSettings) -> Path:
    return settings.storage_dir / HEALTH_FILENAME


def build_application(
    app_settings: AppSettings,
    db_settings: DatabaseSettings,
    telegram_settings: TelegramSettings,
) -> Application:
    database = Database(db_settings)
    userbot = UserbotComponent(telegram_settings)
    status_service = StatusService(database, userbot.status)
    control_bot = ControlBotComponent(
        telegram_settings,
        storage=PostgresStorage(database),
        status_service=status_service,
        timezone=app_settings.tz,
    )
    heartbeat = HeartbeatComponent(
        health_file(app_settings),
        {
            "userbot": lambda: userbot.status().connected,
            "control_bot": lambda: control_bot.is_running,
        },
    )
    components: list[Component] = [
        DatabaseComponent(database),
        userbot,
        control_bot,
        heartbeat,
    ]
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
