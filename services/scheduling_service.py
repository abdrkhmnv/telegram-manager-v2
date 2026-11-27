"""PostgreSQL asosidagi rejalashtiruvchi: rejalashtirilgan va tasodifiy intervalli autopost.

Ishlash tartibi (har ``poll_interval`` soniyada):
1. ``claim_due`` — vaqti kelgan vazifalar ``FOR UPDATE SKIP LOCKED`` bilan atomik egallanadi.
2. Har bir manzil uchun ``scheduled_posts`` da (vazifa, manzil, slot) yozuvi olinadi —
   shu slot shu manzilga allaqachon yuborilgan bo'lsa, qayta yuborilmaydi.
3. Hammasi muvaffaqiyatli bo'lsa — keyingi slot hisoblanadi. Xato bo'lsa — o'sha slot
   eksponensial kutish bilan ``max_retries`` martagacha qayta uriniladi (faqat xato bo'lgan
   manzillarga), so'ng keyingi slotga o'tiladi (bir martalik post ``failed`` bo'ladi).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from core.telegram_errors import describe_error
from database.connection import Database
from database.models import AutopostKind, AutopostTask, Recurrence, RunStatus, TaskStatus
from database.repositories.autopost import (
    AutopostTaskRepository,
    ScheduledPostRepository,
    TaskLogRepository,
)
from services.media_service import MediaService
from services.message_service import SEND_ERRORS, OutgoingContent, send_content
from services.posting_service import template_content
from utils.logger import get_logger
from utils.time_utils import next_daily_run, next_random_run, next_weekly_run, utc_now

logger = get_logger(__name__)

DEFAULT_POLL_INTERVAL = 15.0
DEFAULT_LEASE_SECONDS = 600
RETRY_BASE = timedelta(minutes=2)


def default_worker_id() -> str:
    return f"{socket.gethostname()[:40]}-{os.getpid()}"


def next_slot(task: AutopostTask, after: datetime, tz: ZoneInfo) -> datetime | None:
    """Vazifaning ``after`` dan keyingi bajarilish vaqti (bir martalik uchun ``None``)."""
    if task.kind is AutopostKind.RANDOM:
        if task.min_interval_seconds is None or task.max_interval_seconds is None:
            return None
        return next_random_run(
            after,
            task.min_interval_seconds,
            task.max_interval_seconds,
            tz,
            task.active_from,
            task.active_to,
        )
    if task.recurrence is Recurrence.DAILY and task.time_of_day is not None:
        return next_daily_run(after, task.time_of_day, tz)
    if task.recurrence is Recurrence.WEEKLY and task.time_of_day is not None and task.weekdays_mask:
        return next_weekly_run(after, task.time_of_day, task.weekdays_mask, tz)
    return None


@dataclass(frozen=True, slots=True)
class RunOutcome:
    sent: int
    failed: int
    skipped: int
    error: str | None = None


class SchedulerComponent:
    name = "scheduler"

    def __init__(
        self,
        database: Database,
        client_provider: Callable[[], Any],
        media: MediaService,
        timezone: ZoneInfo,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        send_delay: float = 1.5,
        worker_id: str | None = None,
    ) -> None:
        self._database = database
        self._client = client_provider
        self._media = media
        self._tz = timezone
        self._poll = poll_interval
        self._lease = lease_seconds
        self._delay = send_delay
        self.worker_id = worker_id or default_worker_id()
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="scheduler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Rejalashtiruvchi siklida xato")
            await asyncio.sleep(self._poll)

    async def tick(self, now: datetime | None = None) -> int:
        """Bitta sikl: vaqti kelganlarni egallab, bajaradi. Qaytaradi: bajarilgan vazifalar soni."""
        moment = now or utc_now()
        async with self._database.session() as session:
            claimed = await AutopostTaskRepository(session).claim_due(
                now=moment, worker_id=self.worker_id, lease_seconds=self._lease
            )
        for task in claimed:
            await self.run_task(task.id, moment)
        return len(claimed)

    async def _load(self, task_id: int) -> tuple[AutopostTask | None, Any, int | None]:
        async with self._database.session() as session:
            repo = AutopostTaskRepository(session)
            task = await repo.get_full(task_id)
            if task is None:
                return None, None, None
            template_id: int | None = task.template_id
            item_id: int | None = None
            if task.kind is AutopostKind.RANDOM:
                item = await repo.pick_queue_item(task_id)
                template_id = item.template_id if item else None
                item_id = item.id if item else None
            template = await repo.template(template_id) if template_id else None
        return task, template, item_id

    async def run_task(self, task_id: int, now: datetime) -> RunOutcome:
        task, template, item_id = await self._load(task_id)
        if task is None or task.next_run_at is None:
            return RunOutcome(0, 0, 0, "vazifa topilmadi")
        slot = task.next_run_at
        async with self._database.session() as session:
            log_id = await TaskLogRepository(session).start(task.id, task.name)

        if template is None:
            outcome = RunOutcome(0, 0, 0, "kontent yo'q (navbat bo'sh yoki post o'chirilgan)")
        else:
            outcome = await self._deliver(task, template_content(template), template.id, slot)
            if item_id is not None and outcome.sent:
                async with self._database.session() as session:
                    await AutopostTaskRepository(session).mark_item_posted(item_id, now)

        await self._finish(task, slot, now, outcome)
        status = (
            RunStatus.SUCCESS
            if outcome.failed == 0 and outcome.error is None
            else RunStatus.SKIPPED
            if template is None
            else RunStatus.FAILED
        )
        async with self._database.session() as session:
            await TaskLogRepository(session).finish(
                log_id,
                status,
                finished_at=utc_now(),
                error=outcome.error,
                details={
                    "sent": outcome.sent,
                    "failed": outcome.failed,
                    "skipped": outcome.skipped,
                },
            )
        return outcome

    async def _deliver(
        self, task: AutopostTask, content: OutgoingContent, template_id: int, slot: datetime
    ) -> RunOutcome:
        destinations = [c.telegram_id for c in task.destinations if c.is_accessible]
        sent = failed = skipped = 0
        last_error: str | None = None
        client = self._client()
        for index, destination in enumerate(destinations):
            async with self._database.session() as session:
                post_id = await ScheduledPostRepository(session).claim_occurrence(
                    task_id=task.id,
                    kind=task.kind,
                    template_id=template_id,
                    destination_chat_telegram_id=destination,
                    scheduled_for=slot,
                )
            if post_id is None:
                skipped += 1
                continue
            try:
                message_id = await send_content(client, self._media, destination, content)
            except SEND_ERRORS as exc:  # MediaMissingError ham OSError
                failed += 1
                last_error = describe_error(exc)
                async with self._database.session() as session:
                    await ScheduledPostRepository(session).mark_failed(post_id, last_error)
            else:
                sent += 1
                async with self._database.session() as session:
                    await ScheduledPostRepository(session).mark_sent(
                        post_id, message_id=message_id, sent_at=utc_now()
                    )
            if index < len(destinations) - 1:
                await asyncio.sleep(self._delay)
        if not destinations:
            last_error = "faol manzil yo'q"
        return RunOutcome(sent, failed, skipped, last_error if failed or not destinations else None)

    async def _finish(
        self, task: AutopostTask, slot: datetime, now: datetime, outcome: RunOutcome
    ) -> None:
        succeeded = outcome.failed == 0 and outcome.error is None
        attempts = task.consecutive_failures + 1
        async with self._database.session() as session:
            repo = AutopostTaskRepository(session)
            if not succeeded and outcome.failed and attempts < task.max_retries:
                retry_at = now + RETRY_BASE * (2 ** (attempts - 1))
                await repo.release(
                    task.id,
                    worker_id=self.worker_id,
                    next_run_at=slot,
                    ran_at=now,
                    succeeded=False,
                    retry_at=retry_at,
                )
                logger.warning(
                    "Autopost qayta uriniladi",
                    extra={"task": task.id, "attempt": attempts, "retry_at": retry_at.isoformat()},
                )
                return
            upcoming = next_slot(task, max(now, slot), self._tz)
            status: TaskStatus | None = None
            if upcoming is None:
                status = TaskStatus.COMPLETED if succeeded else TaskStatus.FAILED
            await repo.release(
                task.id,
                worker_id=self.worker_id,
                next_run_at=upcoming,
                ran_at=now,
                succeeded=succeeded,
                status=status,
            )
