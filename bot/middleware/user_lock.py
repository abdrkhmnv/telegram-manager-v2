"""Bir foydalanuvchining xabarlarini ketma-ket qayta ishlash.

Albom (bir nechta media) Telegram'dan alohida xabarlar bo'lib bir vaqtda keladi.
Ular parallel ishlansa, FSM ma'lumotiga yozishda bir-birini "yutib" yuborishi mumkin.
Bu middleware har bir foydalanuvchi uchun xabarlarni navbat bilan bajaradi (rad etmaydi).
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UserLockMiddleware(BaseMiddleware):
    def __init__(self, max_entries: int = 1000) -> None:
        self._locks: OrderedDict[int, asyncio.Lock] = OrderedDict()
        self._max_entries = max_entries

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)
        user_id = event.from_user.id
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
            while len(self._locks) > self._max_entries:
                oldest_id, oldest = next(iter(self._locks.items()))
                if oldest.locked():
                    break
                del self._locks[oldest_id]
        async with lock:
            return await handler(event, data)
