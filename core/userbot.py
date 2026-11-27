"""Yagona Telethon (MTProto) klienti: sessiya, ulanish, qayta ulanish, holat.

Kirish (telefon raqami, kod, 2FA) faqat bir marta ``python main.py login`` orqali
bajariladi. Oddiy ishga tushishda sessiya avtorizatsiyadan o'tmagan bo'lsa,
ilova aniq ko'rsatma bilan to'xtaydi — terminalda savol bermaydi.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telethon import TelegramClient

from app.config import TelegramSettings
from core.exceptions import StartupError
from utils.logger import get_logger, register_secret

logger = get_logger(__name__)

APP_VERSION = "1.0.0"
DEVICE_MODEL = "Telegram Manager v2"
WATCHDOG_INTERVAL = 30.0
RECONNECT_MAX_DELAY = 300.0


class UserbotNotAuthorizedError(StartupError):
    """Sessiya mavjud emas yoki bekor qilingan."""


@dataclass(frozen=True, slots=True)
class UserbotStatus:
    connected: bool
    authorized: bool
    user_id: int | None = None
    display_name: str | None = None
    username: str | None = None


ClientFactory = Callable[[TelegramSettings], Any]


def secure_session_dir(session_dir: Path) -> None:
    """Sessiya katalogini ``700`` ruxsat bilan yaratadi/tuzatadi."""
    session_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(session_dir, 0o700)


def secure_session_file(session_path: Path) -> None:
    """``<nom>.session`` faylini (bo'lsa) ``600`` ruxsatga keltiradi."""
    for suffix in (".session", ".session-journal"):
        candidate = session_path.with_name(session_path.name + suffix)
        if candidate.exists():
            os.chmod(candidate, 0o600)


def build_client(settings: TelegramSettings) -> TelegramClient:
    register_secret(settings.telegram_api_hash.get_secret_value())
    client = TelegramClient(
        str(settings.session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash.get_secret_value(),
        device_model=DEVICE_MODEL,
        app_version=APP_VERSION,
        connection_retries=5,
        retry_delay=2,
        request_retries=3,
        auto_reconnect=True,
        flood_sleep_threshold=60,
        timeout=15,
    )
    # message.text HTML ko'rinishida qaytadi — copy rejimida formatlash saqlanadi.
    client.parse_mode = "html"
    return client


def _display_name(user: Any) -> str:
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    return " ".join(part for part in parts if part) or "—"


class UserbotComponent:
    """Lifecycle komponenti. ``client`` boshqa servislarga shu obyekt orqali beriladi."""

    name = "userbot"

    def __init__(
        self,
        settings: TelegramSettings,
        *,
        client_factory: ClientFactory = build_client,
        watchdog_interval: float = WATCHDOG_INTERVAL,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory
        self._watchdog_interval = watchdog_interval
        self._client: Any = None
        self._watchdog: asyncio.Task[None] | None = None
        self._me: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Userbot hali ishga tushirilmagan")
        return self._client

    async def start(self) -> None:
        secure_session_dir(self._settings.session_dir)
        self._client = self._client_factory(self._settings)
        await self._client.connect()
        secure_session_file(self._settings.session_path)
        if not await self._client.is_user_authorized():
            await self._client.disconnect()
            raise UserbotNotAuthorizedError(
                "Telegram akkaunti ulanmagan. Bir marta bajaring: python main.py login"
            )
        self._me = await self._client.get_me()
        logger.info(
            "Userbot ulandi",
            extra={"user_id": getattr(self._me, "id", None)},
        )
        self._watchdog = asyncio.create_task(self._watch_connection(), name="userbot-watchdog")

    async def stop(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog
            self._watchdog = None
        if self._client is not None:
            await self._client.disconnect()

    async def _watch_connection(self) -> None:
        """Telethon o'zi qayta ulanadi; u taslim bo'lsa — backoff bilan qayta ulanamiz."""
        delay = self._watchdog_interval
        while True:
            await asyncio.sleep(delay)
            if self._client.is_connected():
                delay = self._watchdog_interval
                continue
            logger.warning("Userbot uzildi, qayta ulanilmoqda", extra={"retry_in": delay})
            try:
                await self._client.connect()
            except (OSError, ConnectionError, TimeoutError) as exc:
                logger.warning("Qayta ulanish muvaffaqiyatsiz", extra={"error": type(exc).__name__})
                delay = min(max(delay, 1.0) * 2, RECONNECT_MAX_DELAY)
            else:
                logger.info("Userbot qayta ulandi")
                delay = self._watchdog_interval

    def status(self) -> UserbotStatus:
        if self._client is None:
            return UserbotStatus(connected=False, authorized=False)
        me = self._me
        return UserbotStatus(
            connected=bool(self._client.is_connected()),
            authorized=me is not None,
            user_id=getattr(me, "id", None),
            display_name=_display_name(me) if me is not None else None,
            username=getattr(me, "username", None),
        )
