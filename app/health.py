"""Heartbeat: ishlayotgan ilova holatini faylga yozadi, ``main.py check --app`` uni o'qiydi.

Docker healthcheck alohida jarayonda ishlaydi va Telethon sessiyasini ochmasligi kerak
(SQLite sessiya fayli bloklanadi), shuning uchun holat fayl orqali uzatiladi.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path

from utils.logger import get_logger
from utils.time_utils import ensure_utc, utc_now

logger = get_logger(__name__)

HEALTH_FILENAME = "health.json"
DEFAULT_INTERVAL = 30.0
DEFAULT_MAX_AGE = timedelta(seconds=120)

Probe = Callable[[], bool]


def write_heartbeat(path: Path, components: Mapping[str, bool], now: datetime) -> None:
    payload = {
        "ts": ensure_utc(now).isoformat(),
        "components": dict(components),
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, path)


def read_heartbeat(
    path: Path, *, now: datetime, max_age: timedelta = DEFAULT_MAX_AGE
) -> tuple[bool, str]:
    """``(sog'lommi, izoh)``."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        timestamp = datetime.fromisoformat(payload["ts"])
        components = {str(k): bool(v) for k, v in dict(payload["components"]).items()}
    except FileNotFoundError:
        return False, "heartbeat fayli yo'q (ilova ishlamayapti)"
    except (OSError, ValueError, KeyError, TypeError):
        return False, "heartbeat fayli buzilgan"
    age = ensure_utc(now) - ensure_utc(timestamp)
    if age > max_age:
        return False, f"heartbeat eskirgan ({int(age.total_seconds())} s)"
    failed = sorted(name for name, ok in components.items() if not ok)
    if failed:
        return False, "ishlamayotgan komponentlar: " + ", ".join(failed)
    return True, "barcha komponentlar ishlayapti: " + ", ".join(sorted(components))


class HeartbeatComponent:
    name = "heartbeat"

    def __init__(
        self, path: Path, probes: Mapping[str, Probe], interval: float = DEFAULT_INTERVAL
    ) -> None:
        if interval <= 0:
            raise ValueError("interval musbat bo'lishi kerak")
        self._path = path
        self._probes = dict(probes)
        self._interval = interval
        self._task: asyncio.Task[None] | None = None

    def beat(self) -> None:
        components: dict[str, bool] = {}
        for name, probe in self._probes.items():
            try:
                components[name] = bool(probe())
            except Exception:  # probe xatosi = komponent ishlamayapti
                components[name] = False
        write_heartbeat(self._path, components, utc_now())

    async def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.beat()
        self._task = asyncio.create_task(self._loop(), name="heartbeat")

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                self.beat()
            except OSError:
                logger.exception("Heartbeat faylini yozib bo'lmadi")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()
