"""Statistika — faqat bazadagi haqiqiy yozuvlardan (soxta hisoblagichlarsiz)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Select, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from database.connection import Database
from database.models import (
    AutopostKind,
    AutopostTask,
    DeliveryStatus,
    ForwardLog,
    ForwardMode,
    ForwardRule,
    MessageLog,
    MessageOperation,
    PostStatus,
    RuleStatus,
    ScheduledPost,
    TaskStatus,
)
from utils.time_utils import local_to_utc, to_local, utc_now


@dataclass(frozen=True, slots=True)
class Totals:
    messages_sent: int
    native_forwards: int
    copy_deliveries: int
    scheduled_posts: int
    random_posts: int
    failed: int

    @property
    def successful(self) -> int:
        return (
            self.messages_sent
            + self.native_forwards
            + self.copy_deliveries
            + self.scheduled_posts
            + self.random_posts
        )


@dataclass(frozen=True, slots=True)
class Statistics:
    all_time: Totals
    today: Totals
    active_tasks: int
    paused_tasks: int
    active_rules: int
    paused_rules: int
    daily: list[tuple[date, int]] = field(default_factory=list)

    @property
    def week_total(self) -> int:
        return sum(count for _, count in self.daily)


async def _count(session: AsyncSession, statement: Select[tuple[int]]) -> int:
    return int(await session.scalar(statement) or 0)


def _since(
    column: InstrumentedAttribute[datetime], since: datetime | None
) -> list[ColumnElement[bool]]:
    return [column >= since] if since is not None else []


async def _totals(session: AsyncSession, since: datetime | None) -> Totals:

    sent = await _count(
        session,
        select(func.count())
        .select_from(MessageLog)
        .where(
            MessageLog.operation == MessageOperation.SEND,
            MessageLog.status == DeliveryStatus.SUCCESS,
            *_since(MessageLog.created_at, since),
        ),
    )
    forwards: dict[ForwardMode, int] = {}
    for mode in ForwardMode:
        forwards[mode] = await _count(
            session,
            select(func.count())
            .select_from(ForwardLog)
            .where(
                ForwardLog.mode == mode,
                ForwardLog.status == DeliveryStatus.SUCCESS,
                *_since(ForwardLog.created_at, since),
            ),
        )
    posts: dict[AutopostKind, int] = {}
    for kind in AutopostKind:
        posts[kind] = await _count(
            session,
            select(func.count())
            .select_from(ScheduledPost)
            .where(
                ScheduledPost.kind == kind,
                ScheduledPost.status == PostStatus.SENT,
                *_since(ScheduledPost.created_at, since),
            ),
        )
    failed = (
        await _count(
            session,
            select(func.count())
            .select_from(MessageLog)
            .where(
                MessageLog.status == DeliveryStatus.FAILED,
                *_since(MessageLog.created_at, since),
            ),
        )
        + await _count(
            session,
            select(func.count())
            .select_from(ForwardLog)
            .where(
                ForwardLog.status == DeliveryStatus.FAILED,
                *_since(ForwardLog.created_at, since),
            ),
        )
        + await _count(
            session,
            select(func.count())
            .select_from(ScheduledPost)
            .where(
                ScheduledPost.status == PostStatus.FAILED,
                *_since(ScheduledPost.created_at, since),
            ),
        )
    )
    return Totals(
        messages_sent=sent,
        native_forwards=forwards[ForwardMode.NATIVE],
        copy_deliveries=forwards[ForwardMode.COPY],
        scheduled_posts=posts[AutopostKind.SCHEDULED],
        random_posts=posts[AutopostKind.RANDOM],
        failed=failed,
    )


class StatisticsService:
    def __init__(self, database: Database, timezone: ZoneInfo) -> None:
        self._database = database
        self._tz = timezone

    def _local_midnight(self, now: datetime, days_back: int = 0) -> datetime:
        local_day = to_local(now, self._tz).date() - timedelta(days=days_back)
        return local_to_utc(datetime.combine(local_day, datetime.min.time()), self._tz)

    async def collect(self, now: datetime | None = None) -> Statistics:
        moment = now or utc_now()
        today_start = self._local_midnight(moment)
        week_start = self._local_midnight(moment, days_back=6)
        async with self._database.session() as session:
            all_time = await _totals(session, None)
            today = await _totals(session, today_start)
            task_rows = await session.execute(
                select(AutopostTask.status, func.count()).group_by(AutopostTask.status)
            )
            task_counts: dict[TaskStatus, int] = {s: int(n) for s, n in task_rows.all()}
            rule_rows = await session.execute(
                select(ForwardRule.status, func.count()).group_by(ForwardRule.status)
            )
            rule_counts: dict[RuleStatus, int] = {s: int(n) for s, n in rule_rows.all()}
            daily = await self._daily(session, week_start)
        return Statistics(
            all_time=all_time,
            today=today,
            active_tasks=int(task_counts.get(TaskStatus.ACTIVE, 0)),
            paused_tasks=int(task_counts.get(TaskStatus.PAUSED, 0)),
            active_rules=int(rule_counts.get(RuleStatus.ACTIVE, 0)),
            paused_rules=int(rule_counts.get(RuleStatus.PAUSED, 0)),
            daily=daily,
        )

    async def _daily(self, session: AsyncSession, since: datetime) -> list[tuple[date, int]]:
        """Oxirgi 7 kun (mahalliy sana bo'yicha) muvaffaqiyatli amallar soni."""
        events = union_all(
            select(MessageLog.created_at.label("at")).where(
                MessageLog.operation == MessageOperation.SEND,
                MessageLog.status == DeliveryStatus.SUCCESS,
                MessageLog.created_at >= since,
            ),
            select(ForwardLog.created_at.label("at")).where(
                ForwardLog.status == DeliveryStatus.SUCCESS, ForwardLog.created_at >= since
            ),
            select(ScheduledPost.created_at.label("at")).where(
                ScheduledPost.status == PostStatus.SENT, ScheduledPost.created_at >= since
            ),
        ).subquery()
        local_day = func.date(func.timezone(literal(self._tz.key), events.c.at))
        rows = await session.execute(
            select(local_day, func.count()).group_by(local_day).order_by(local_day)
        )
        counts = {day: int(count) for day, count in rows.all()}
        first = to_local(since, self._tz).date()
        return [
            (first + timedelta(days=i), counts.get(first + timedelta(days=i), 0)) for i in range(7)
        ]
