"""Ilovani yig'ish: sozlamalar -> log -> servislar -> komponentlar -> lifecycle.

Komponentlar tartibi: baza -> userbot -> forwarder -> rejalashtiruvchi -> Control Bot -> heartbeat.
To'xtatish teskari tartibda (avval panel, oxirida baza).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import AppSettings, DatabaseSettings, TelegramSettings
from app.health import HEALTH_FILENAME, HeartbeatComponent
from app.lifecycle import Component, LifecycleManager, install_signal_handlers
from bot.context import Services
from bot.storage import PostgresStorage
from core.control_bot import ControlBotComponent
from core.exceptions import MigrationOutOfDateError
from core.userbot import UserbotComponent
from database.connection import Database
from database.migration_check import MigrationStatus, get_migration_status
from services.autopost_service import AutopostService
from services.chat_service import ChatService
from services.forwarding_service import ForwarderComponent, ForwardRuleService
from services.media_service import MediaService
from services.message_service import MessageService
from services.scheduling_service import SchedulerComponent
from services.statistics_service import StatisticsService
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
    services: Services
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
    tz = app_settings.tz
    database = Database(db_settings)
    userbot = UserbotComponent(telegram_settings)

    def client() -> Any:
        return userbot.client

    media = MediaService(database, app_settings.storage_dir, app_settings.max_upload_size_bytes)
    removed = media.cleanup_temporary()
    if removed:
        logger.info("Vaqtinchalik fayllar tozalandi", extra={"count": removed})

    forwarder = ForwarderComponent(database, client)
    scheduler = SchedulerComponent(database, client, media, tz)
    status = StatusService(database, userbot.status)
    services = Services(
        status=status,
        chats=ChatService(database, client),
        messages=MessageService(database, client, media),
        media=media,
        rules=ForwardRuleService(database),
        autopost=AutopostService(database, tz),
        stats=StatisticsService(database, tz),
        timezone=tz,
    )
    services.rules.on_change(forwarder.reload)
    control_bot = ControlBotComponent(
        telegram_settings, storage=PostgresStorage(database), services=services
    )
    status.add_component("forwarder", lambda: forwarder.is_running)
    status.add_component("scheduler", lambda: scheduler.is_running)
    status.add_component("control_bot", lambda: control_bot.is_running)

    heartbeat = HeartbeatComponent(
        health_file(app_settings),
        {
            "userbot": lambda: userbot.status().connected,
            "forwarder": lambda: forwarder.is_running,
            "scheduler": lambda: scheduler.is_running,
            "control_bot": lambda: control_bot.is_running,
        },
    )
    components: list[Component] = [
        DatabaseComponent(database),
        userbot,
        forwarder,
        scheduler,
        control_bot,
        heartbeat,
    ]
    return Application(
        settings=app_settings,
        database=database,
        services=services,
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
