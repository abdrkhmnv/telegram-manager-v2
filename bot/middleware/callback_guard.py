"""Takroriy callback bosilishidan himoya.

* Bir xil tugma qisqa vaqt ichida qayta bosilsa (double tap) — e'tiborsiz qoldiriladi.
* Bir foydalanuvchining callback'lari ketma-ket bajariladi: oldingisi tugamaguncha
  yangisi "kuting" javobini oladi. Bu bir amalning parallel ikki marta bajarilishini oldini oladi.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from bot import texts

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class CallbackGuardMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        window: float = 1.0,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if window <= 0 or max_entries <= 0:
            raise ValueError("window va max_entries musbat bo'lishi kerak")
        self._window = window
        self._max_entries = max_entries
        self._clock = clock
        self._recent: OrderedDict[tuple[int, str], float] = OrderedDict()
        self._locks: OrderedDict[int, asyncio.Lock] = OrderedDict()

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        user_id = event.from_user.id
        key = (user_id, event.data or "")
        now = self._clock()
        last = self._recent.get(key)
        if last is not None and now - last < self._window:
            await event.answer()
            return None
        self._remember(key, now)

        lock = self._lock_for(user_id)
        if lock.locked():
            await event.answer(texts.BUSY)
            return None
        async with lock:
            return await handler(event, data)

    def _remember(self, key: tuple[int, str], now: float) -> None:
        self._recent[key] = now
        self._recent.move_to_end(key)
        while len(self._recent) > self._max_entries:
            self._recent.popitem(last=False)

    def _lock_for(self, user_id: int) -> asyncio.Lock:
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
            while len(self._locks) > self._max_entries:
                oldest_id, oldest = next(iter(self._locks.items()))
                if oldest.locked():
                    break
                del self._locks[oldest_id]
        return lock
