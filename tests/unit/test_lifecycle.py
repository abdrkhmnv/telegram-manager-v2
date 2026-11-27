from __future__ import annotations

import asyncio

import pytest

from app.lifecycle import LifecycleManager


class FakeComponent:
    def __init__(
        self,
        name: str,
        journal: list[str],
        *,
        fail_start: bool = False,
        fail_stop: bool = False,
        hang_stop: bool = False,
    ) -> None:
        self.name = name
        self._journal = journal
        self._fail_start = fail_start
        self._fail_stop = fail_stop
        self._hang_stop = hang_stop

    async def start(self) -> None:
        if self._fail_start:
            raise RuntimeError(f"{self.name} start failed")
        self._journal.append(f"start:{self.name}")

    async def stop(self) -> None:
        if self._hang_stop:
            await asyncio.sleep(10)
        if self._fail_stop:
            raise RuntimeError(f"{self.name} stop failed")
        self._journal.append(f"stop:{self.name}")


async def test_start_in_order_stop_in_reverse() -> None:
    journal: list[str] = []
    manager = LifecycleManager([FakeComponent("db", journal), FakeComponent("bot", journal)])
    shutdown = asyncio.Event()
    shutdown.set()
    await manager.run_until(shutdown)
    assert journal == ["start:db", "start:bot", "stop:bot", "stop:db"]
    assert manager.started_names == []


async def test_failed_start_rolls_back_started_components() -> None:
    journal: list[str] = []
    manager = LifecycleManager(
        [
            FakeComponent("db", journal),
            FakeComponent("userbot", journal, fail_start=True),
            FakeComponent("bot", journal),
        ]
    )
    with pytest.raises(RuntimeError, match="userbot start failed"):
        await manager.start()
    assert journal == ["start:db", "stop:db"]


async def test_stop_continues_after_errors_and_timeouts() -> None:
    journal: list[str] = []
    manager = LifecycleManager(
        [
            FakeComponent("a", journal),
            FakeComponent("b", journal, fail_stop=True),
            FakeComponent("c", journal, hang_stop=True),
        ],
        stop_timeout=0.05,
    )
    await manager.start()
    await manager.stop()
    assert journal == ["start:a", "start:b", "start:c", "stop:a"]
    assert manager.started_names == []


def test_rejects_duplicate_names_and_bad_timeout() -> None:
    journal: list[str] = []
    with pytest.raises(ValueError):
        LifecycleManager([FakeComponent("x", journal), FakeComponent("x", journal)])
    with pytest.raises(ValueError):
        LifecycleManager([], stop_timeout=0)
