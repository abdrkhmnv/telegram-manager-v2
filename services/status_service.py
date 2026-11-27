"""Tizim holati: userbot, baza, migratsiya, ish vaqti."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from core.userbot import UserbotStatus
from database.connection import Database
from database.migration_check import get_migration_status
from utils.time_utils import utc_now

APP_VERSION = "0.2.0"


@dataclass(frozen=True, slots=True)
class SystemStatus:
    version: str
    started_at: datetime
    checked_at: datetime
    database_ok: bool
    migrations_current: bool
    migration_revision: str | None
    userbot: UserbotStatus

    @property
    def uptime_seconds(self) -> int:
        return max(0, int((self.checked_at - self.started_at).total_seconds()))


class StatusService:
    def __init__(
        self,
        database: Database,
        userbot_status: Callable[[], UserbotStatus],
        started_at: datetime | None = None,
    ) -> None:
        self._database = database
        self._userbot_status = userbot_status
        self._started_at = started_at or utc_now()

    async def collect(self) -> SystemStatus:
        database_ok = True
        migrations_current = False
        revision: str | None = None
        try:
            await self._database.ping()
            migration = await get_migration_status(self._database)
            migrations_current = migration.is_current
            revision = ", ".join(sorted(migration.current)) or None
        except (SQLAlchemyError, OSError, TimeoutError):
            database_ok = False
        return SystemStatus(
            version=APP_VERSION,
            started_at=self._started_at,
            checked_at=utc_now(),
            database_ok=database_ok,
            migrations_current=migrations_current,
            migration_revision=revision,
            userbot=self._userbot_status(),
        )
