from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AutopostKind, AutopostTask, PostStatus, ScheduledPost, TaskStatus
from utils.helpers import truncate
from utils.time_utils import ensure_utc

_ERROR_LIMIT = 1000
_MAX_WORKER_ID = 64


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

    async def set_status(self, task_id: int, status: TaskStatus) -> bool:
        """Holatni o'zgartiradi (pauza, davom ettirish, bekor qilish).

        Ijara bekor qilinmaydi: hozir bajarilayotgan ishchi o'z ishini tugatadi,
        lekin vazifa ``active`` bo'lmagani uchun keyingi safar egallanmaydi.
        """
        result = await self._session.execute(
            update(AutopostTask).where(AutopostTask.id == task_id).values(status=status)
        )
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
    ) -> bool:
        """Ijarani bo'shatadi va keyingi bajarilish vaqtini yozadi.

        Faqat ijara egasi bo'shata oladi; boshqa ishchi uchun ``False``.
        """
        values: dict[str, object] = {
            "locked_by": None,
            "locked_until": None,
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
        )
        return bool(getattr(result, "rowcount", 0))


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
