"""Komponentlarni tartib bilan ishga tushirish va to'xtatish.

Komponentlar ro'yxatdagi tartibda ishga tushadi va teskari tartibda to'xtaydi.
Biror komponent ishga tushmasa, oldin ishga tushganlari to'xtatiladi va xato
yuqoriga uzatiladi. 2-bosqichda Telethon userbot va Control Bot shu menejerga
komponent sifatida ulanadi.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Sequence
from typing import Protocol

from utils.logger import get_logger

logger = get_logger(__name__)


class Component(Protocol):
    name: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class LifecycleManager:
    def __init__(self, components: Sequence[Component], stop_timeout: float = 30.0) -> None:
        if stop_timeout <= 0:
            raise ValueError("stop_timeout musbat bo'lishi kerak")
        names = [component.name for component in components]
        if len(names) != len(set(names)):
            raise ValueError("Komponent nomlari takrorlanmasligi kerak")
        self._components = list(components)
        self._started: list[Component] = []
        self._stop_timeout = stop_timeout

    @property
    def started_names(self) -> list[str]:
        return [component.name for component in self._started]

    async def start(self) -> None:
        for component in self._components:
            logger.info("Komponent ishga tushirilmoqda", extra={"component": component.name})
            try:
                await component.start()
            except BaseException:
                logger.exception("Komponent ishga tushmadi", extra={"component": component.name})
                await self.stop()
                raise
            self._started.append(component)
            logger.info("Komponent ishga tushdi", extra={"component": component.name})

    async def stop(self) -> None:
        while self._started:
            component = self._started.pop()
            try:
                await asyncio.wait_for(component.stop(), timeout=self._stop_timeout)
                logger.info("Komponent to'xtatildi", extra={"component": component.name})
            except TimeoutError:
                logger.error(
                    "Komponent belgilangan vaqtda to'xtamadi",
                    extra={"component": component.name, "timeout": self._stop_timeout},
                )
            except Exception:
                logger.exception(
                    "Komponentni to'xtatishda xato", extra={"component": component.name}
                )

    async def run_until(self, shutdown: asyncio.Event) -> None:
        """Hammasini ishga tushiradi, ``shutdown`` kutadi, so'ng to'xtatadi."""
        await self.start()
        try:
            await shutdown.wait()
        finally:
            await self.stop()


def install_signal_handlers(shutdown: asyncio.Event) -> None:
    """SIGINT/SIGTERM kelganda ``shutdown`` hodisasini o'rnatadi."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(sig, shutdown.set)
