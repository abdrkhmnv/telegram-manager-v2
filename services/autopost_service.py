"""Autopost vazifalarini boshqarish (yaratish, pauza, bekor qilish, kontentni almashtirish)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from database.connection import Database
from database.models import (
    AutopostKind,
    AutopostQueueItem,
    AutopostTask,
    PostStatus,
    PostTemplate,
    Recurrence,
    ScheduledPost,
    TaskStatus,
)
from database.repositories.autopost import AutopostTaskRepository
from database.repositories.templates import TemplateRepository
from services.message_service import plain_preview
from services.scheduling_service import next_slot
from utils.time_utils import ensure_utc, utc_now
from utils.validators import InputValidationError, validate_interval


@dataclass(frozen=True, slots=True)
class DraftPost:
    text: str | None
    media_ids: tuple[int, ...] = ()


def _name(prefix: str, text: str | None) -> str:
    preview = plain_preview(text)[:40]
    return f"{prefix}: {preview} #{uuid.uuid4().hex[:4]}"[:100]


class AutopostService:
    def __init__(self, database: Database, timezone: ZoneInfo) -> None:
        self._database = database
        self._tz = timezone

    async def list_tasks(self, kind: AutopostKind) -> list[AutopostTask]:
        async with self._database.session() as session:
            return await AutopostTaskRepository(session).list_by_kind(kind)

    async def get(self, task_id: int) -> AutopostTask | None:
        async with self._database.session() as session:
            return await AutopostTaskRepository(session).get_full(task_id)

    async def template(self, template_id: int) -> PostTemplate | None:
        async with self._database.session() as session:
            return await AutopostTaskRepository(session).template(template_id)

    async def queue(self, task_id: int) -> list[AutopostQueueItem]:
        async with self._database.session() as session:
            return await AutopostTaskRepository(session).queue_items(task_id)

    async def stats(self, task_id: int) -> dict[PostStatus, int]:
        async with self._database.session() as session:
            return await AutopostTaskRepository(session).stats(task_id)

    async def recent_posts(self, task_id: int) -> list[ScheduledPost]:
        async with self._database.session() as session:
            return await AutopostTaskRepository(session).recent_posts(task_id)

    async def create_scheduled(
        self,
        post: DraftPost,
        destination_ids: Sequence[int],
        *,
        recurrence: Recurrence,
        at: time,
        run_at: datetime | None = None,
        weekdays_mask: int | None = None,
    ) -> AutopostTask:
        if not destination_ids:
            raise InputValidationError("Kamida bitta manzil tanlang")
        now = utc_now()
        if recurrence is Recurrence.ONCE:
            if run_at is None:
                raise InputValidationError("Sana va vaqt kerak")
            run_at = ensure_utc(run_at)
            if run_at <= now:
                raise InputValidationError("Vaqt kelajakda bo'lishi kerak")
        if recurrence is Recurrence.WEEKLY and not weekdays_mask:
            raise InputValidationError("Kamida bitta hafta kunini tanlang")
        async with self._database.session() as session:
            template = await TemplateRepository(session).create(
                text=post.text, media_ids=post.media_ids
            )
            task = AutopostTask(
                name=_name("Post", post.text),
                kind=AutopostKind.SCHEDULED,
                recurrence=recurrence,
                run_at=run_at,
                time_of_day=at,
                weekdays_mask=weekdays_mask if recurrence is Recurrence.WEEKLY else None,
                template_id=template.id,
            )
            task.next_run_at = run_at if run_at else next_slot(task, now, self._tz)
            repo = AutopostTaskRepository(session)
            await repo.set_destinations(task, destination_ids)
            await repo.add(task)
            return task

    async def create_random(
        self,
        posts: Sequence[DraftPost],
        destination_ids: Sequence[int],
        *,
        min_seconds: int,
        max_seconds: int,
        active_from: time | None,
        active_to: time | None,
    ) -> AutopostTask:
        validate_interval(min_seconds, max_seconds)
        if not destination_ids:
            raise InputValidationError("Kamida bitta manzil tanlang")
        if not posts:
            raise InputValidationError("Navbatga kamida bitta post qo'shing")
        async with self._database.session() as session:
            repo = AutopostTaskRepository(session)
            task = AutopostTask(
                name=_name("Random", posts[0].text),
                kind=AutopostKind.RANDOM,
                min_interval_seconds=min_seconds,
                max_interval_seconds=max_seconds,
                active_from=active_from,
                active_to=active_to,
            )
            task.next_run_at = next_slot(task, utc_now(), self._tz)
            await repo.set_destinations(task, destination_ids)
            await repo.add(task)
            templates = TemplateRepository(session)
            for post in posts:
                template = await templates.create(text=post.text, media_ids=post.media_ids)
                await repo.add_queue_item(task.id, template.id)
            return task

    async def add_queue_posts(self, task_id: int, posts: Sequence[DraftPost]) -> int:
        async with self._database.session() as session:
            repo = AutopostTaskRepository(session)
            templates = TemplateRepository(session)
            for post in posts:
                template = await templates.create(text=post.text, media_ids=post.media_ids)
                await repo.add_queue_item(task_id, template.id)
        return len(posts)

    async def replace_content(self, task_id: int, post: DraftPost) -> bool:
        async with self._database.session() as session:
            task = await AutopostTaskRepository(session).get(task_id)
            if task is None or task.template_id is None:
                return False
            return await TemplateRepository(session).replace_content(
                task.template_id, text=post.text, media_ids=post.media_ids
            )

    async def pause(self, task_id: int) -> bool:
        async with self._database.session() as session:
            return await AutopostTaskRepository(session).set_status(task_id, TaskStatus.PAUSED)

    async def resume(self, task_id: int) -> bool:
        """Davom ettirishda keyingi vaqt hozirdan boshlab qayta hisoblanadi.

        Bir martalik post vaqti o'tib ketgan bo'lsa — darhol (keyingi siklda) yuboriladi.
        """
        now = utc_now()
        async with self._database.session() as session:
            repo = AutopostTaskRepository(session)
            task = await repo.get(task_id)
            if task is None:
                return False
            upcoming: datetime | None
            if task.kind is AutopostKind.SCHEDULED and task.recurrence is Recurrence.ONCE:
                upcoming = max(task.run_at or now, now)
            else:
                upcoming = next_slot(task, now, self._tz)
            return await repo.set_status(
                task_id, TaskStatus.ACTIVE, next_run_at=upcoming, consecutive_failures=0
            )

    async def cancel(self, task_id: int) -> bool:
        async with self._database.session() as session:
            return await AutopostTaskRepository(session).set_status(
                task_id, TaskStatus.CANCELLED, next_run_at=None
            )

    async def delete(self, task_id: int) -> bool:
        async with self._database.session() as session:
            repo = AutopostTaskRepository(session)
            task = await repo.get(task_id)
            if task is None:
                return False
            template_ids = [task.template_id] if task.template_id else []
            template_ids += [item.template_id for item in await repo.queue_items(task_id)]
            await repo.delete(task_id)
            templates = TemplateRepository(session)
            for template_id in template_ids:
                await templates.delete(template_id)
            return True
