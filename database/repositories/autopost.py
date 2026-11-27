from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    AutopostKind,
    AutopostQueueItem,
    AutopostTask,
    Chat,
    PostStatus,
    PostTemplate,
    PostTemplateMedia,
    RunStatus,
    ScheduledPost,
    TaskLog,
    TaskStatus,
)
from utils.helpers import truncate
from utils.time_utils import ensure_utc

_ERROR_LIMIT = 1000
_MAX_WORKER_ID = 64
_system_random = random.SystemRandom()


class AutopostTaskRepository:
    """Autopost vazifalari va ularni atomik egallash (lease) mexanizmi."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: AutopostTask) -> AutopostTask:
        self._session.add(task)
        await self._session.flush()
        return task

    async def get(self, task_id: int) -> AutopostTask | None:
        return await self._session.get(AutopostTask, task_id)

    async def get_full(self, task_id: int) -> AutopostTask | None:
        """Manzillar bilan birga (``lazy="raise"`` bo'lgani uchun aniq yuklanadi)."""
        return await self._session.scalar(
            select(AutopostTask)
            .options(selectinload(AutopostTask.destinations))
            .where(AutopostTask.id == task_id)
        )

    async def list_by_kind(self, kind: AutopostKind) -> list[AutopostTask]:
        rows = await self._session.scalars(
            select(AutopostTask)
            .options(selectinload(AutopostTask.destinations))
            .where(AutopostTask.kind == kind)
            .order_by(AutopostTask.id.desc())
        )
        return list(rows.all())

    async def set_destinations(self, task: AutopostTask, chat_ids: Sequence[int]) -> None:
        chats = await self._session.scalars(select(Chat).where(Chat.id.in_(list(chat_ids))))
        task.destinations = list(chats.all())

    async def set_status(self, task_id: int, status: TaskStatus, **values: Any) -> bool:
        """Holatni o'zgartiradi (pauza, davom ettirish, bekor qilish).

        Ijara bekor qilinmaydi: hozir bajarilayotgan ishchi o'z ishini tugatadi,
        lekin vazifa ``active`` bo'lmagani uchun keyingi safar egallanmaydi.
        """
        result = await self._session.execute(
            update(AutopostTask)
            .where(AutopostTask.id == task_id)
            .values(status=status, **values)
            .execution_options(synchronize_session=False)
        )
        return bool(getattr(result, "rowcount", 0))

    async def delete(self, task_id: int) -> bool:
        result = await self._session.execute(delete(AutopostTask).where(AutopostTask.id == task_id))
        return bool(getattr(result, "rowcount", 0))

    async def claim_due(
        self, *, now: datetime, worker_id: str, lease_seconds: int, limit: int = 10
    ) -> list[AutopostTask]:
        """Vaqti kelgan faol vazifalarni atomik egallaydi.

        ``FOR UPDATE SKIP LOCKED`` tufayli parallel ishchilar bir vazifani
        ikki marta ololmaydi. Ijarasi tugagan (masalan, jarayon qulagan)
        vazifalar qayta egallanadi — bu ilova qayta ishga tushganda tiklanishni ta'minlaydi.
        """
        if not worker_id or len(worker_id) > _MAX_WORKER_ID:
            raise ValueError("worker_id 1..64 belgidan iborat bo'lishi kerak")
        if lease_seconds <= 0 or limit <= 0:
            raise ValueError("lease_seconds va limit musbat bo'lishi kerak")
        now_utc = ensure_utc(now)
        due_ids = (
            select(AutopostTask.id)
            .where(
                AutopostTask.status == TaskStatus.ACTIVE,
                AutopostTask.next_run_at.is_not(None),
                AutopostTask.next_run_at <= now_utc,
                or_(AutopostTask.locked_until.is_(None), AutopostTask.locked_until < now_utc),
            )
            .order_by(AutopostTask.next_run_at, AutopostTask.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        statement = (
            update(AutopostTask)
            .where(AutopostTask.id.in_(due_ids))
            .values(locked_by=worker_id, locked_until=now_utc + timedelta(seconds=lease_seconds))
            .returning(AutopostTask)
            .execution_options(synchronize_session=False, populate_existing=True)
        )
        claimed = list((await self._session.scalars(statement)).all())
        claimed.sort(key=lambda task: (task.next_run_at or now_utc, task.id))
        return claimed

    async def release(
        self,
        task_id: int,
        *,
        worker_id: str,
        next_run_at: datetime | None,
        ran_at: datetime,
        succeeded: bool,
        status: TaskStatus | None = None,
        retry_at: datetime | None = None,
    ) -> bool:
        """Ijarani bo'shatadi va keyingi bajarilish vaqtini yozadi.

        ``retry_at`` berilsa, vazifa shu vaqtgacha qayta egallanmaydi (``next_run_at``
        o'zgarmagan holda — ya'ni xuddi shu slot qayta uriniladi). Faqat ijara egasi bo'shata oladi.
        """
        values: dict[str, object] = {
            "locked_by": None,
            "locked_until": ensure_utc(retry_at) if retry_at else None,
            "next_run_at": ensure_utc(next_run_at) if next_run_at else None,
            "last_run_at": ensure_utc(ran_at),
            "consecutive_failures": 0 if succeeded else AutopostTask.consecutive_failures + 1,
        }
        if status is not None:
            values["status"] = status
        result = await self._session.execute(
            update(AutopostTask)
            .where(AutopostTask.id == task_id, AutopostTask.locked_by == worker_id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return bool(getattr(result, "rowcount", 0))

    # ------------------------------------------------------------ content queue
    async def add_queue_item(self, task_id: int, template_id: int) -> AutopostQueueItem:
        item = AutopostQueueItem(task_id=task_id, template_id=template_id)
        self._session.add(item)
        await self._session.flush()
        return item

    async def queue_items(self, task_id: int) -> list[AutopostQueueItem]:
        rows = await self._session.scalars(
            select(AutopostQueueItem)
            .where(AutopostQueueItem.task_id == task_id)
            .order_by(AutopostQueueItem.id)
        )
        return list(rows.all())

    async def pick_queue_item(
        self, task_id: int, rng: random.Random | None = None
    ) -> AutopostQueueItem | None:
        """Eng kam yuborilgan elementlar orasidan tasodifiy tanlaydi.

        Bir nechta element bo'lsa, oxirgi yuborilgani ketma-ket qaytarilmaydi.
        """
        items = await self.queue_items(task_id)
        if not items:
            return None
        lowest = min(item.times_posted for item in items)
        candidates = [item for item in items if item.times_posted == lowest]
        if len(items) > 1:
            posted = [i for i in items if i.last_posted_at is not None]
            last = max(posted, key=lambda i: ensure_utc(i.last_posted_at)) if posted else None  # type: ignore[arg-type]
            filtered = [i for i in candidates if last is None or i.id != last.id]
            if filtered:
                candidates = filtered
            elif last is not None:
                candidates = [i for i in items if i.id != last.id]
        return (rng or _system_random).choice(candidates)

    async def mark_item_posted(self, item_id: int, at: datetime) -> None:
        await self._session.execute(
            update(AutopostQueueItem)
            .where(AutopostQueueItem.id == item_id)
            .values(times_posted=AutopostQueueItem.times_posted + 1, last_posted_at=ensure_utc(at))
            .execution_options(synchronize_session=False)
        )

    async def template(self, template_id: int) -> PostTemplate | None:
        return await self._session.scalar(
            select(PostTemplate)
            .options(selectinload(PostTemplate.media_items).selectinload(PostTemplateMedia.media))
            .where(PostTemplate.id == template_id)
        )

    async def stats(self, task_id: int) -> dict[PostStatus, int]:
        rows = await self._session.execute(
            select(ScheduledPost.status, func.count())
            .where(ScheduledPost.task_id == task_id)
            .group_by(ScheduledPost.status)
        )
        return {status: int(count) for status, count in rows.all()}

    async def recent_posts(self, task_id: int, limit: int = 10) -> list[ScheduledPost]:
        rows = await self._session.scalars(
            select(ScheduledPost)
            .where(ScheduledPost.task_id == task_id)
            .order_by(ScheduledPost.created_at.desc(), ScheduledPost.id.desc())
            .limit(limit)
        )
        return list(rows.all())


class ScheduledPostRepository:
    """Vazifa bajarilishlarining (occurrence) idempotent yozuvlari."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_occurrence(
        self,
        *,
        task_id: int,
        kind: AutopostKind,
        template_id: int | None,
        destination_chat_telegram_id: int,
        scheduled_for: datetime,
    ) -> int | None:
        """Yangi yozuv ID'si yoki, agar u allaqachon mavjud bo'lsa, ``None``."""
        statement = (
            pg_insert(ScheduledPost)
            .values(
                task_id=task_id,
                kind=kind,
                template_id=template_id,
                destination_chat_telegram_id=destination_chat_telegram_id,
                scheduled_for=ensure_utc(scheduled_for),
                status=PostStatus.PENDING,
                attempts=0,
            )
            .on_conflict_do_nothing(constraint="uq_scheduled_posts_occurrence")
            .returning(ScheduledPost.id)
        )
        return await self._session.scalar(statement)

    async def claim_occurrence(
        self,
        *,
        task_id: int,
        kind: AutopostKind,
        template_id: int | None,
        destination_chat_telegram_id: int,
        scheduled_for: datetime,
    ) -> int | None:
        """Yuborilishi kerak bo'lgan yozuv ID'si; shu slot shu manzilga yuborilgan bo'lsa ``None``.

        Avvalgi urinishda xato bo'lgan yozuv qayta qaytariladi (faqat muvaffaqiyatsizlar
        qayta yuboriladi — muvaffaqiyatli manzillarga takror yuborilmaydi).
        """
        created = await self.create_occurrence(
            task_id=task_id,
            kind=kind,
            template_id=template_id,
            destination_chat_telegram_id=destination_chat_telegram_id,
            scheduled_for=scheduled_for,
        )
        if created is not None:
            return created
        row = (
            await self._session.execute(
                select(ScheduledPost.id, ScheduledPost.status).where(
                    ScheduledPost.task_id == task_id,
                    ScheduledPost.destination_chat_telegram_id == destination_chat_telegram_id,
                    ScheduledPost.scheduled_for == ensure_utc(scheduled_for),
                )
            )
        ).first()
        if row is None or row.status in (PostStatus.SENT, PostStatus.CANCELLED):
            return None
        return int(row.id)

    async def mark_sent(self, post_id: int, *, message_id: int | None, sent_at: datetime) -> None:
        await self._session.execute(
            update(ScheduledPost)
            .where(ScheduledPost.id == post_id)
            .values(
                status=PostStatus.SENT,
                sent_message_id=message_id,
                sent_at=ensure_utc(sent_at),
                attempts=ScheduledPost.attempts + 1,
                error=None,
            )
        )

    async def mark_failed(self, post_id: int, error: str) -> None:
        await self._session.execute(
            update(ScheduledPost)
            .where(ScheduledPost.id == post_id)
            .values(
                status=PostStatus.FAILED,
                attempts=ScheduledPost.attempts + 1,
                error=truncate(error, _ERROR_LIMIT),
            )
        )


class TaskLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, task_id: int | None, task_name: str) -> int:
        entry = TaskLog(task_id=task_id, task_name=task_name[:100], status=RunStatus.STARTED)
        self._session.add(entry)
        await self._session.flush()
        return entry.id

    async def finish(
        self,
        log_id: int,
        status: RunStatus,
        *,
        finished_at: datetime,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        await self._session.execute(
            update(TaskLog)
            .where(TaskLog.id == log_id)
            .values(
                status=status,
                finished_at=ensure_utc(finished_at),
                error=truncate(error, _ERROR_LIMIT) if error else None,
                details=details or {},
            )
        )
