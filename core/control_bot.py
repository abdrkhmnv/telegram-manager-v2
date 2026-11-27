"""Control Bot (Bot API, aiogram) lifecycle komponenti."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError
from aiogram.fsm.storage.base import BaseStorage
from aiogram.types import BotCommand, BotCommandScopeChat

from app.config import TelegramSettings
from bot.dispatcher import build_dispatcher
from core.exceptions import StartupError
from services.status_service import StatusService
from utils.logger import get_logger, register_secret

logger = get_logger(__name__)

BOT_COMMANDS = (
    BotCommand(command="start", description="Bosh menyu"),
    BotCommand(command="help", description="Yordam"),
)
STOP_TIMEOUT = 15.0


def build_bot(settings: TelegramSettings) -> Bot:
    token = settings.bot_token.get_secret_value()
    register_secret(token)
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


class ControlBotComponent:
    name = "control_bot"

    def __init__(
        self,
        settings: TelegramSettings,
        *,
        storage: BaseStorage,
        status_service: StatusService,
        timezone: ZoneInfo,
        bot_factory: Callable[[TelegramSettings], Bot] = build_bot,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._status_service = status_service
        self._timezone = timezone
        self._bot_factory = bot_factory
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._polling: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._polling is not None and not self._polling.done()

    async def start(self) -> None:
        bot = self._bot_factory(self._settings)
        self._bot = bot
        try:
            me = await bot.get_me()
        except TelegramUnauthorizedError as exc:
            await bot.session.close()
            raise StartupError("BOT_TOKEN noto'g'ri yoki bekor qilingan (@BotFather)") from exc
        logger.info("Control Bot ulandi", extra={"bot_username": me.username})

        await self._set_commands(bot)
        dispatcher = build_dispatcher(
            owner_id=self._settings.owner_telegram_id,
            storage=self._storage,
            status_service=self._status_service,
            timezone=self._timezone,
        )
        self._dispatcher = dispatcher
        self._polling = asyncio.create_task(
            dispatcher.start_polling(
                bot,
                handle_signals=False,
                close_bot_session=False,
                allowed_updates=dispatcher.resolve_used_update_types(),
            ),
            name="control-bot-polling",
        )
        self._polling.add_done_callback(self._on_polling_done)

    async def _set_commands(self, bot: Bot) -> None:
        """Buyruqlar faqat egasining chatida ko'rinadi.

        Egasi botga hali /start yozmagan bo'lsa Telegram xato qaytaradi — bu
        ishga tushishga to'sqinlik qilmaydi.
        """
        try:
            await bot.set_my_commands(
                list(BOT_COMMANDS),
                scope=BotCommandScopeChat(chat_id=self._settings.owner_telegram_id),
            )
        except TelegramAPIError as exc:
            logger.warning(
                "Bot buyruqlarini o'rnatib bo'lmadi (egasi botga /start yozganmi?)",
                extra={"error": type(exc).__name__},
            )

    @staticmethod
    def _on_polling_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Control Bot polling to'xtadi", exc_info=exc)

    async def stop(self) -> None:
        if self._polling is not None:
            if self._dispatcher is not None:
                with contextlib.suppress(RuntimeError):  # polling hali boshlanmagan bo'lsa
                    await self._dispatcher.stop_polling()
            done, _ = await asyncio.wait({self._polling}, timeout=STOP_TIMEOUT)
            if not done:
                self._polling.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._polling
            self._polling = None
        if self._bot is not None:
            await self._bot.session.close()
            self._bot = None
