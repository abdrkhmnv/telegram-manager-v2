from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import Database
from database.models import (
    ActivityLog,
    AutopostKind,
    AutopostTask,
    ChatType,
    DeliveryStatus,
    ForwardMode,
    ForwardRule,
    PostStatus,
    Recurrence,
    ScheduledPost,
    TaskStatus,
)
from database.repositories import (
    ActivityLogRepository,
    AutopostTaskRepository,
    ChatRepository,
    ChatSnapshot,
    ForwardLogRepository,
    ScheduledPostRepository,
    SettingsRepository,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------- settings
async def test_settings_upsert(session: AsyncSession) -> None:
    repo = SettingsRepository(session)
    assert await repo.get("ui.page_size", 10) == 10
    await repo.set("ui.page_size", 20)
    await repo.set("ui.page_size", 25)
    assert await repo.get("ui.page_size") == 25
    await repo.set("forward.defaults", {"mode": "copy", "dedupe": True})
    assert await repo.get("forward.defaults") == {"mode": "copy", "dedupe": True}
    assert await repo.delete("ui.page_size") is True
    assert await repo.delete("ui.page_size") is False
    with pytest.raises(ValueError):
        await repo.set("x", None)


# ------------------------------------------------------------------- chats
async def test_chat_upsert_preserves_user_flags(session: AsyncSession) -> None:
    repo = ChatRepository(session)
    count = await repo.upsert_many(
        [
            ChatSnapshot(-1001, ChatType.CHANNEL, "Yangiliklar", "news_uz", 1500),
            ChatSnapshot(-1001, ChatType.CHANNEL, "Yangiliklar (dublikat)", "news_uz", 1501),
            ChatSnapshot(42, ChatType.PRIVATE, "Ali"),
        ],
        synced_at=NOW,
    )
    assert count == 2
    channel = await repo.get_by_telegram_id(-1001)
    assert channel is not None and channel.title == "Yangiliklar (dublikat)"
    assert await repo.set_saved(channel.id, True)

    await repo.upsert_many(
        [ChatSnapshot(-1001, ChatType.CHANNEL, "Yangiliklar 2.0", "news_uz", 1600)],
        synced_at=NOW + timedelta(hours=1),
    )
    session.expire_all()
    refreshed = await repo.get_by_telegram_id(-1001)
    assert refreshed is not None
    assert (refreshed.title, refreshed.members_count, refreshed.is_saved) == (
        "Yangiliklar 2.0",
        1600,
        True,
    )
    assert refreshed.last_synced_at == NOW + timedelta(hours=1)


async def test_chat_search_pagination_and_like_escaping(session: AsyncSession) -> None:
    repo = ChatRepository(session)
    await repo.upsert_many(
        [
            ChatSnapshot(1, ChatType.GROUP, "Python Uzbekistan"),
            ChatSnapshot(2, ChatType.SUPERGROUP, "python_dev", "python_dev"),
            ChatSnapshot(3, ChatType.CHANNEL, "100% chegirma"),
            ChatSnapshot(4, ChatType.CHANNEL, "1000 chegirma"),
        ],
        synced_at=NOW,
    )
    assert {c.telegram_id for c in await repo.search("python")} == {1, 2}
    assert [c.telegram_id for c in await repo.search("@python_dev")] == [2]
    assert [c.telegram_id for c in await repo.search("100%")] == [3]
    assert await repo.count(chat_types=(ChatType.CHANNEL,)) == 2
    first = await repo.search(limit=2, offset=0)
    second = await repo.search(limit=2, offset=2)
    assert len(first) == 2 and len(second) == 2
    assert {c.id for c in first}.isdisjoint({c.id for c in second})


# -------------------------------------------------------------- forwarding
async def _rule(session: AsyncSession) -> ForwardRule:
    rule = ForwardRule(name="test", mode=ForwardMode.COPY)
    session.add(rule)
    await session.flush()
    return rule


async def test_forward_reserve_is_idempotent(session: AsyncSession) -> None:
    rule = await _rule(session)
    repo = ForwardLogRepository(session)
    key = {
        "rule_id": rule.id,
        "mode": ForwardMode.COPY,
        "source_chat_telegram_id": -100,
        "source_message_id": 7,
        "destination_chat_telegram_id": -200,
        "content_hash": "a" * 64,
    }
    first = await repo.reserve(**key)
    assert first is not None
    assert await repo.reserve(**key) is None
    assert await repo.reserve(**{**key, "destination_chat_telegram_id": -300}) is not None

    await repo.mark_failed(first, "FloodWait " * 200)
    log = await repo.get(first)
    assert log is not None
    await session.refresh(log)
    assert (log.status, log.attempts, len(log.error or "")) == (DeliveryStatus.FAILED, 1, 1000)

    await repo.mark_success(first, destination_message_id=99)
    await session.refresh(log)
    assert (log.status, log.attempts, log.error) == (DeliveryStatus.SUCCESS, 2, None)


async def test_forward_duplicate_content_detection(session: AsyncSession) -> None:
    rule = await _rule(session)
    repo = ForwardLogRepository(session)
    log_id = await repo.reserve(
        rule_id=rule.id,
        mode=ForwardMode.NATIVE,
        source_chat_telegram_id=-100,
        source_message_id=1,
        destination_chat_telegram_id=-200,
        content_hash="b" * 64,
    )
    assert log_id is not None
    since = datetime.now(UTC) - timedelta(days=1)
    assert not await repo.has_recent_duplicate(-200, "b" * 64, since)
    await repo.mark_success(log_id, 5)
    assert await repo.has_recent_duplicate(-200, "b" * 64, since)
    assert not await repo.has_recent_duplicate(-999, "b" * 64, since)


# ---------------------------------------------------------------- autopost
def _task(name: str, next_run_at: datetime | None, **overrides: object) -> AutopostTask:
    values: dict[str, object] = {
        "name": name,
        "kind": AutopostKind.SCHEDULED,
        "recurrence": Recurrence.DAILY,
        "time_of_day": time(9, 0),
        "next_run_at": next_run_at,
        **overrides,
    }
    return AutopostTask(**values)


async def _seed_tasks(database: Database) -> None:
    async with database.session() as session:
        repo = AutopostTaskRepository(session)
        for index in range(5):
            await repo.add(_task(f"due-{index}", NOW - timedelta(minutes=index)))
        await repo.add(_task("future", NOW + timedelta(hours=1)))
        await repo.add(_task("paused", NOW - timedelta(hours=1), status=TaskStatus.PAUSED))
        await repo.add(_task("unscheduled", None))


async def test_claim_due_only_active_and_due(database: Database) -> None:
    await _seed_tasks(database)
    async with database.session() as session:
        claimed = await AutopostTaskRepository(session).claim_due(
            now=NOW, worker_id="w1", lease_seconds=300, limit=10
        )
    assert [task.name for task in claimed] == [f"due-{i}" for i in (4, 3, 2, 1, 0)]
    assert all(task.locked_by == "w1" for task in claimed)
    assert all(task.locked_until == NOW + timedelta(seconds=300) for task in claimed)


async def test_concurrent_workers_never_share_a_task(database: Database) -> None:
    await _seed_tasks(database)

    async def claim(worker: str) -> set[int]:
        async with database.session() as session:
            tasks = await AutopostTaskRepository(session).claim_due(
                now=NOW, worker_id=worker, lease_seconds=300, limit=3
            )
            await asyncio.sleep(0.2)  # tranzaksiyani ochiq ushlab turish
            return {task.id for task in tasks}

    first, second = await asyncio.gather(claim("a"), claim("b"))
    assert first.isdisjoint(second)
    assert len(first | second) == 5


async def test_expired_lease_is_reclaimed_after_crash(database: Database) -> None:
    await _seed_tasks(database)
    async with database.session() as session:
        repo = AutopostTaskRepository(session)
        crashed = await repo.claim_due(now=NOW, worker_id="crashed", lease_seconds=60, limit=10)
    assert len(crashed) == 5

    async with database.session() as session:
        repo = AutopostTaskRepository(session)
        assert (
            await repo.claim_due(now=NOW + timedelta(seconds=30), worker_id="w2", lease_seconds=60)
            == []
        )
        recovered = await repo.claim_due(
            now=NOW + timedelta(seconds=61), worker_id="w2", lease_seconds=60
        )
    assert len(recovered) == 5


async def test_release_only_by_lease_owner(database: Database) -> None:
    await _seed_tasks(database)
    async with database.session() as session:
        repo = AutopostTaskRepository(session)
        task = (await repo.claim_due(now=NOW, worker_id="owner", lease_seconds=60, limit=1))[0]
        next_run = NOW + timedelta(days=1)
        assert not await repo.release(
            task.id, worker_id="intruder", next_run_at=next_run, ran_at=NOW, succeeded=True
        )
        assert await repo.release(
            task.id, worker_id="owner", next_run_at=next_run, ran_at=NOW, succeeded=False
        )
        await session.refresh(task)
        assert (task.locked_by, task.locked_until, task.next_run_at) == (None, None, next_run)
        assert task.consecutive_failures == 1
        assert await repo.set_status(task.id, TaskStatus.PAUSED)


async def test_task_check_constraints(database: Database) -> None:
    with pytest.raises(IntegrityError):
        async with database.session() as session:
            session.add(AutopostTask(name="bad-random", kind=AutopostKind.RANDOM))
    with pytest.raises(IntegrityError):
        async with database.session() as session:
            session.add(
                AutopostTask(
                    name="bad-interval",
                    kind=AutopostKind.RANDOM,
                    min_interval_seconds=600,
                    max_interval_seconds=60,
                )
            )


async def test_scheduled_occurrence_is_idempotent(session: AsyncSession) -> None:
    task = await AutopostTaskRepository(session).add(_task("daily", NOW))
    repo = ScheduledPostRepository(session)
    args = {
        "task_id": task.id,
        "kind": AutopostKind.SCHEDULED,
        "template_id": None,
        "destination_chat_telegram_id": -100,
        "scheduled_for": NOW,
    }
    post_id = await repo.create_occurrence(**args)
    assert post_id is not None
    assert await repo.create_occurrence(**args) is None
    await repo.mark_sent(post_id, message_id=11, sent_at=NOW)
    post = await session.scalar(select(ScheduledPost).where(ScheduledPost.id == post_id))
    assert post is not None
    await session.refresh(post)
    assert (post.status, post.sent_message_id, post.attempts) == (PostStatus.SENT, 11, 1)


# ---------------------------------------------------------------- activity
async def test_activity_log(session: AsyncSession) -> None:
    repo = ActivityLogRepository(session)
    await repo.add("rule.created", actor_telegram_id=1, details={"rule_id": 5})
    await repo.add("rule.deleted", actor_telegram_id=1)
    recent = await repo.recent(10)
    assert {entry.action for entry in recent} == {"rule.created", "rule.deleted"}
    assert all(isinstance(entry, ActivityLog) for entry in recent)
    with pytest.raises(ValueError):
        await repo.add("", actor_telegram_id=None)
