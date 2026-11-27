"""Egasi tekshiruvi — har bir update uchun (xabar, callback va boshqalar)."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.permissions import is_owner
from utils.logger import get_logger

logger = get_logger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

_LOG_INTERVAL = 60.0
_MAX_TRACKED = 1000


class OwnerOnlyMiddleware(BaseMiddleware):
    """Egasidan boshqa hammaning update'larini jimgina tashlab yuboradi.

    * Faqat Telegram bergan ``event_from_user`` ishlatiladi — callback ma'lumotiga
      ishonilmaydi.
    * Faqat shaxsiy chat (egasi bilan bot o'rtasida) qabul qilinadi.
    * Begona urinishlar logga yoziladi (bir foydalanuvchi uchun daqiqada ko'pi bilan bir marta).
    """

    def __init__(self, owner_id: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        if owner_id <= 0:
            raise ValueError("owner_id musbat bo'lishi kerak")
        self._owner_id = owner_id
        self._clock = clock
        self._last_logged: OrderedDict[int | None, float] = OrderedDict()

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        user_id = getattr(user, "id", None)
        if not is_owner(user_id, self._owner_id):
            self._log_rejection(user_id)
            return None
        chat = data.get("event_chat")
        if chat is not None and getattr(chat, "type", None) != "private":
            return None
        return await handler(event, data)

    def _log_rejection(self, user_id: int | None) -> None:
        now = self._clock()
        last = self._last_logged.get(user_id)
        if last is not None and now - last < _LOG_INTERVAL:
            return
        self._last_logged[user_id] = now
        self._last_logged.move_to_end(user_id)
        while len(self._last_logged) > _MAX_TRACKED:
            self._last_logged.popitem(last=False)
        logger.warning("Ruxsatsiz foydalanuvchi panelga murojaat qildi", extra={"user_id": user_id})
