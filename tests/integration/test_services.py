"""Servislar haqiqiy PostgreSQL va soxta Telethon klienti bilan."""

from __future__ import annotations

import time as clock
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from database.connection import Database
from database.models import (
    AutopostKind,
    AutopostTask,
    Chat,
    ChatType,
    DeliveryStatus,
    ForwardLog,
    ForwardMode,
    MediaType,
    MessageLog,
    PostStatus,
    PostTemplate,
    Recurrence,
    RuleStatus,
    ScheduledPost,
    TaskStatus,
)
from database.repositories.autopost import AutopostTaskRepository
from database.repositories.chats import ChatRepository, ChatSnapshot
from services.autopost_service import AutopostService, DraftPost
from services.chat_service import ChatService
from services.forwarding_service import ForwarderComponent, ForwardRuleService
from services.media_service import IncomingMedia, MediaInUseError, MediaService
from services.message_service import MessageService, OutgoingContent
from services.scheduling_service import SchedulerComponent
from services.statistics_service import StatisticsService
from tests.helpers.fakes import FakeBot, FakeClient, entity, tg_message
from utils.validators import InputValidationError

TZ = ZoneInfo("Asia/Tashkent")
SOURCE, DEST_A, DEST_B = -1001, -1002, -1003


async def seed_chats(database: Database) -> dict[int, int]:
    """Telegram ID -> bazadagi ID."""
    async with database.session() as session:
        repo = ChatRepository(session)
        await repo.upsert_many(
            [
                ChatSnapshot(SOURCE, ChatType.CHANNEL, "Manba"),
                ChatSnapshot(DEST_A, ChatType.CHANNEL, "Manzil A"),
                ChatSnapshot(DEST_B, ChatType.SUPERGROUP, "Manzil B"),
            ],
            datetime.now(UTC),
        )
        rows = await session.execute(select(Chat.telegram_id, Chat.id))
        return dict(rows.all())  # type: ignore[arg-type]


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def media(database: Database, tmp_path: Path) -> MediaService:
    return MediaService(database, tmp_path / "storage", 50 * 1024 * 1024)


# --------------------------------------------------------------------- chats
async def test_sync_dialogs_maps_types_and_hides_missing(
    database: Database, client: FakeClient
) -> None:
    client.dialogs = [
        SimpleNamespace(entity=entity("User", 42, first_name="Ali", username="ali"), name="Ali"),
        SimpleNamespace(entity=entity("Chat", 77, title="Oila"), name="Oila"),
        SimpleNamespace(
            entity=entity("Channel", 555, title="Kanal", megagroup=False), name="Kanal"
        ),
        SimpleNamespace(entity=entity("Channel", 556, title="Super", megagroup=True), name="Super"),
        SimpleNamespace(entity=entity("ChannelForbidden", 9, title="Taqiq"), name="Taqiq"),
        SimpleNamespace(entity=entity("Channel", 557, title="Chiqqan", left=True), name="Chiqqan"),
    ]
    service = ChatService(database, lambda: client)
    result = await service.sync_dialogs()
    assert result.total == 4
    assert result.by_type == {
        ChatType.PRIVATE: 1,
        ChatType.GROUP: 1,
        ChatType.CHANNEL: 1,
        ChatType.SUPERGROUP: 1,
    }
    async with database.session() as session:
        repo = ChatRepository(session)
        assert (await repo.get_by_telegram_id(-1000000000555)).chat_type is ChatType.CHANNEL  # type: ignore[union-attr]
        assert (await repo.get_by_telegram_id(-77)).chat_type is ChatType.GROUP  # type: ignore[union-attr]

    client.dialogs = client.dialogs[:1]
    result = await service.sync_dialogs()
    assert result.marked_inaccessible == 3
    page = await service.page(None, 0)
    assert [c.telegram_id for c in page.chats] == [42]


async def test_categories(database: Database) -> None:
    ids = await seed_chats(database)
    service = ChatService(database, lambda: None)
    category = await service.create_category("  Ish   kanallari ", chat_id=ids[DEST_A])
    assert category.name == "Ish kanallari"
    assert await service.chat_category_ids(ids[DEST_A]) == {category.id}
    assert await service.toggle_category(ids[DEST_A], category.id) is False
    assert await service.toggle_category(ids[DEST_B], category.id) is True
    _, chats = await service.category(category.id)
    assert [c.telegram_id for c in chats] == [DEST_B]
    with pytest.raises(ValueError):
        await service.create_category("ish kanallari".upper() * 10)
    assert await service.delete_category(category.id)


# ------------------------------------------------------------------- media
async def test_media_store_dedupe_validate_delete(database: Database, media: MediaService) -> None:
    bot = FakeBot({"f1": b"same-bytes", "f2": b"same-bytes"})
    first = await media.store_from_bot(
        bot, IncomingMedia("f1", MediaType.PHOTO, "image/jpeg", 10, "a.jpg")
    )
    second = await media.store_from_bot(
        bot, IncomingMedia("f2", MediaType.PHOTO, "image/jpeg", 10, "b.jpg")
    )
    assert first.id == second.id
    path = await media.path_for(first)
    assert path.read_bytes() == b"same-bytes"
    assert oct(path.stat().st_mode)[-3:] == "600"
    assert not list((path.parents[2] / "tmp").glob("*.part"))

    with pytest.raises(InputValidationError):
        await media.store_from_bot(
            bot, IncomingMedia("x", MediaType.DOCUMENT, "application/octet-stream", 5, "virus.exe")
        )
    with pytest.raises(InputValidationError):
        await media.store_from_bot(
            bot, IncomingMedia("x", MediaType.PHOTO, "image/jpeg", 30 * 1024 * 1024)
        )
    with pytest.raises(InputValidationError):
        await media.store_from_bot(bot, IncomingMedia("x", MediaType.VIDEO, "video/x-msvideo", 5))

    service = AutopostService(database, TZ)
    ids = await seed_chats(database)
    task = await service.create_scheduled(
        DraftPost("caption", (first.id,)), [ids[DEST_A]], recurrence=Recurrence.DAILY, at=time(9)
    )
    with pytest.raises(MediaInUseError):
        await media.delete(first.id)
    await service.delete(task.id)
    assert await media.delete(first.id)
    assert not path.exists()


# ---------------------------------------------------------------- messaging
async def test_send_history_edit_delete(
    database: Database, client: FakeClient, media: MediaService
) -> None:
    from telethon.errors import ChatWriteForbiddenError

    ids = await seed_chats(database)
    client.fail_for[DEST_B] = [ChatWriteForbiddenError(request=None)]
    service = MessageService(database, lambda: client, media, delay_seconds=0)
    progress: list[tuple[int, int]] = []

    async def on_progress(done: int, total: int) -> None:
        progress.append((done, total))

    report = await service.send(
        OutgoingContent(text="<b>Salom</b>"),
        [ids[DEST_A], ids[DEST_B]],
        progress=on_progress,
    )
    assert report.sent == 1
    assert report.failed[0].error == "Bu chatga yozish huquqi yo'q"
    assert progress == [(1, 2), (2, 2)]
    _, _peer, args, kwargs = client.sent_to(DEST_A)[0]
    assert args == ("<b>Salom</b>",) and kwargs["parse_mode"] == "html"

    items, _, _ = await service.history(0)
    assert len(items) == 1 and items[0].preview == "Salom"
    assert await service.edit(items[0].id, "Yangi") is None
    assert client.calls[-1][0] == "edit_message"
    assert await service.delete(items[0].id) is None
    items, _, _ = await service.history(0)
    assert items == []

    with pytest.raises(ValueError):
        await service.send(OutgoingContent(text="  "), [ids[DEST_A]])


# ---------------------------------------------------------------- forwarder
async def make_forwarder(
    database: Database, client: FakeClient, mode: ForwardMode, **rule_fields: object
) -> tuple[ForwarderComponent, ForwardRuleService, int]:
    ids = await seed_chats(database)
    rules = ForwardRuleService(database)
    rule = await rules.create("qoida", mode, [ids[SOURCE]], [ids[DEST_A], ids[DEST_B]])
    if rule_fields:
        await rules.update(rule.id, **rule_fields)
    forwarder = ForwarderComponent(database, lambda: client, delay_seconds=0, retry_base=0)
    rules.on_change(forwarder.reload)
    await forwarder.reload()
    return forwarder, rules, rule.id


async def logs(database: Database) -> list[ForwardLog]:
    async with database.session() as session:
        return list((await session.scalars(select(ForwardLog).order_by(ForwardLog.id))).all())


async def test_native_forward_is_idempotent(database: Database, client: FakeClient) -> None:
    forwarder, _, _ = await make_forwarder(database, client, ForwardMode.NATIVE)
    message = tg_message(10, "yangilik")
    assert await forwarder.process(SOURCE, [message]) == 2
    assert await forwarder.process(SOURCE, [message]) == 0  # qayta kelsa — yuborilmaydi
    forwards = [c for c in client.calls if c[0] == "forward_messages"]
    assert len(forwards) == 2
    assert forwards[0][3]["from_peer"] == SOURCE
    assert {log.status for log in await logs(database)} == {DeliveryStatus.SUCCESS}


async def test_copy_mode_with_header_footer_and_album(
    database: Database, client: FakeClient
) -> None:
    forwarder, _, _ = await make_forwarder(
        database, client, ForwardMode.COPY, header_text="<b>Bosh</b>", footer_text="Oxir"
    )
    await forwarder.process(SOURCE, [tg_message(11, "matn")])
    text_call = client.sent_to(DEST_A)[0]
    assert text_call[0] == "send_message"
    assert text_call[2][0] == "<b>Bosh</b>\n\nmatn\n\nOxir"
    album = [
        tg_message(12, "izoh", photo_id=1, grouped_id=5),
        tg_message(13, photo_id=2, grouped_id=5),
    ]
    await forwarder.process(SOURCE, album)
    file_call = client.sent_to(DEST_B)[-1]
    assert file_call[0] == "send_file"
    assert file_call[3]["caption"][0] == "<b>Bosh</b>\n\nizoh\n\nOxir"
    assert len(file_call[2][0]) == 2


async def test_copy_without_extras_copies_message_object(
    database: Database, client: FakeClient
) -> None:
    forwarder, _, _ = await make_forwarder(database, client, ForwardMode.COPY)
    message = tg_message(20, "asl")
    await forwarder.process(SOURCE, [message])
    assert client.sent_to(DEST_A)[0][2][0] is message


async def test_protected_filtered_duplicate_and_loop(
    database: Database, client: FakeClient
) -> None:
    forwarder, rules, rule_id = await make_forwarder(
        database,
        client,
        ForwardMode.COPY,
        include_keywords=["aksiya"],
        exclude_keywords=["reklama"],
        duplicate_detection=True,
    )
    assert await forwarder.process(SOURCE, [tg_message(30, "aksiya", noforwards=True)]) == 0
    assert await forwarder.process(SOURCE, [tg_message(31, "oddiy xabar")]) == 0
    assert await forwarder.process(SOURCE, [tg_message(32, "aksiya reklama")]) == 0
    assert await forwarder.process(SOURCE, [tg_message(33, "Katta AKSIYA")]) == 2
    assert await forwarder.process(SOURCE, [tg_message(34, "Katta AKSIYA")]) == 0  # takror
    statuses = [(log.source_message_id, log.status, log.error) for log in await logs(database)]
    assert (
        30,
        DeliveryStatus.SKIPPED,
        "himoyalangan kontent (forward/nusxalash taqiqlangan)",
    ) in statuses
    assert (34, DeliveryStatus.SKIPPED, "takroriy kontent") in statuses

    # Forwarder'ning o'zi yuborgan xabar manbada paydo bo'lsa — qayta yo'naltirilmaydi.
    forwarder._remember_sent(SOURCE, SimpleNamespace(id=999))
    assert await forwarder.process(SOURCE, [tg_message(999, "aksiya yana")]) == 0

    # Qoida pauzaga olinsa, runtime darhol yangilanadi.
    await rules.set_status(rule_id, RuleStatus.PAUSED)
    assert forwarder.rule_count == 0


async def test_transient_errors_are_retried(database: Database, client: FakeClient) -> None:
    forwarder, _, _ = await make_forwarder(database, client, ForwardMode.NATIVE)
    client.fail_for[DEST_A] = [ConnectionError("tarmoq"), ConnectionError("tarmoq")]
    from telethon.errors import ChatWriteForbiddenError

    client.fail_for[DEST_B] = [ChatWriteForbiddenError(request=None)]
    assert await forwarder.process(SOURCE, [tg_message(40, "x")]) == 1
    by_dest = {log.destination_chat_telegram_id: log for log in await logs(database)}
    assert by_dest[DEST_A].status is DeliveryStatus.SUCCESS
    assert by_dest[DEST_B].status is DeliveryStatus.FAILED
    assert by_dest[DEST_B].attempts == 1


# ---------------------------------------------------------------- scheduler
async def make_scheduler(
    database: Database, client: FakeClient, media: MediaService
) -> SchedulerComponent:
    return SchedulerComponent(database, lambda: client, media, TZ, send_delay=0, worker_id="w1")


async def task_row(database: Database, task_id: int) -> AutopostTask:
    async with database.session() as session:
        task = await session.get(AutopostTask, task_id)
        assert task is not None
        return task


async def test_once_post_retries_only_failed_destination_then_completes(
    database: Database, client: FakeClient, media: MediaService
) -> None:
    ids = await seed_chats(database)
    service = AutopostService(database, TZ)
    run_at = datetime.now(UTC) + timedelta(minutes=5)
    task = await service.create_scheduled(
        DraftPost("Bir martalik"),
        [ids[DEST_A], ids[DEST_B]],
        recurrence=Recurrence.ONCE,
        at=time(0),
        run_at=run_at,
    )
    scheduler = await make_scheduler(database, client, media)
    assert await scheduler.tick(now=run_at - timedelta(seconds=1)) == 0

    client.fail_for[DEST_B] = [ConnectionError("tarmoq")]
    assert await scheduler.tick(now=run_at + timedelta(seconds=1)) == 1
    row = await task_row(database, task.id)
    assert row.status is TaskStatus.ACTIVE and row.consecutive_failures == 1
    assert row.next_run_at == run_at and row.locked_until is not None

    # Kutish vaqti tugamaguncha qayta urinilmaydi.
    assert await scheduler.tick(now=run_at + timedelta(seconds=30)) == 0
    assert await scheduler.tick(now=row.locked_until + timedelta(seconds=1)) == 1
    row = await task_row(database, task.id)
    assert row.status is TaskStatus.COMPLETED and row.next_run_at is None
    assert len(client.sent_to(DEST_A)) == 1  # muvaffaqiyatli manzilga takror yuborilmadi
    assert len(client.sent_to(DEST_B)) == 1
    stats = await service.stats(task.id)
    assert stats == {PostStatus.SENT: 2}


async def test_daily_post_advances_and_survives_restart(
    database: Database, client: FakeClient, media: MediaService
) -> None:
    ids = await seed_chats(database)
    service = AutopostService(database, TZ)
    task = await service.create_scheduled(
        DraftPost("Kunlik"), [ids[DEST_A]], recurrence=Recurrence.DAILY, at=time(9, 0)
    )
    first_slot = (await task_row(database, task.id)).next_run_at
    assert first_slot is not None and first_slot.astimezone(TZ).time() == time(9, 0)

    # "Qulagan" ishchi vazifani egallab, hech narsa yubormay to'xtadi.
    async with database.session() as session:
        claimed = await AutopostTaskRepository(session).claim_due(
            now=first_slot, worker_id="crashed", lease_seconds=60
        )
    assert len(claimed) == 1
    scheduler = await make_scheduler(database, client, media)
    assert await scheduler.tick(now=first_slot + timedelta(seconds=30)) == 0  # ijara hali bor
    assert await scheduler.tick(now=first_slot + timedelta(seconds=61)) == 1  # tiklandi
    row = await task_row(database, task.id)
    assert row.next_run_at == first_slot + timedelta(days=1)
    assert row.status is TaskStatus.ACTIVE and row.locked_by is None
    assert len(client.sent_to(DEST_A)) == 1


async def test_random_post_picks_queue_and_respects_window(
    database: Database, client: FakeClient, media: MediaService
) -> None:
    ids = await seed_chats(database)
    service = AutopostService(database, TZ)
    task = await service.create_random(
        [DraftPost("A"), DraftPost("B")],
        [ids[DEST_A]],
        min_seconds=600,
        max_seconds=1200,
        active_from=time(9, 0),
        active_to=time(22, 0),
    )
    scheduler = await make_scheduler(database, client, media)
    sent_texts = []
    for _ in range(2):
        slot = (await task_row(database, task.id)).next_run_at
        assert slot is not None
        assert time(9, 0) <= slot.astimezone(TZ).time() < time(22, 0)
        assert await scheduler.tick(now=slot) == 1
        sent_texts.append(client.sent_to(DEST_A)[-1][2][0])
    assert sorted(sent_texts) == ["A", "B"]  # takrorlanmasdan navbat bo'yicha
    queue = await service.queue(task.id)
    assert [item.times_posted for item in queue] == [1, 1]


async def test_pause_resume_cancel_delete(database: Database) -> None:
    ids = await seed_chats(database)
    service = AutopostService(database, TZ)
    task = await service.create_scheduled(
        DraftPost("x"), [ids[DEST_A]], recurrence=Recurrence.WEEKLY, at=time(10), weekdays_mask=1
    )
    assert await service.pause(task.id)
    assert (await task_row(database, task.id)).status is TaskStatus.PAUSED
    assert await service.resume(task.id)
    row = await task_row(database, task.id)
    assert row.status is TaskStatus.ACTIVE and row.next_run_at.astimezone(TZ).weekday() == 0  # type: ignore[union-attr]
    assert await service.cancel(task.id)
    assert (await task_row(database, task.id)).next_run_at is None
    assert await service.delete(task.id)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PostTemplate)) == 0
    with pytest.raises(InputValidationError):
        await service.create_scheduled(
            DraftPost("x"),
            [ids[DEST_A]],
            recurrence=Recurrence.ONCE,
            at=time(1),
            run_at=datetime.now(UTC) - timedelta(minutes=1),
        )


# --------------------------------------------------------------- statistics
async def test_statistics_come_from_records(
    database: Database, client: FakeClient, media: MediaService
) -> None:
    forwarder, _, _ = await make_forwarder(database, client, ForwardMode.NATIVE)
    await forwarder.process(SOURCE, [tg_message(50, "a")])
    ids = await seed_chats(database)
    messages = MessageService(database, lambda: client, media, delay_seconds=0)
    await messages.send(OutgoingContent(text="salom"), [ids[DEST_A]])
    stats = await StatisticsService(database, TZ).collect()
    assert stats.all_time.native_forwards == 2
    assert stats.all_time.messages_sent == 1
    assert stats.today.successful == 3
    assert stats.active_rules == 1
    assert stats.week_total == 3
    assert len(stats.daily) == 7


# -------------------------------------------------------------- performance
@pytest.mark.integration
async def test_bulk_operations_stay_fast(database: Database) -> None:
    """Kichik yuklama tekshiruvi — aniq quvvat da'vosi emas, keskin sekinlashuvdan himoya."""
    started = clock.perf_counter()
    async with database.session() as session:
        await ChatRepository(session).upsert_many(
            [ChatSnapshot(-(10**12) - i, ChatType.CHANNEL, f"Kanal {i}") for i in range(3000)],
            datetime.now(UTC),
        )
    now = datetime.now(UTC)
    async with database.session() as session:
        repo = AutopostTaskRepository(session)
        for i in range(300):
            await repo.add(
                AutopostTask(
                    name=f"t{i}",
                    kind=AutopostKind.SCHEDULED,
                    recurrence=Recurrence.DAILY,
                    time_of_day=time(9),
                    next_run_at=now - timedelta(minutes=1),
                )
            )
    claimed = 0
    while True:
        async with database.session() as session:
            batch = await AutopostTaskRepository(session).claim_due(
                now=now, worker_id="perf", lease_seconds=60, limit=50
            )
        if not batch:
            break
        claimed += len(batch)
    elapsed = clock.perf_counter() - started
    assert claimed == 300
    assert elapsed < 30, elapsed
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(MessageLog)) == 0
        assert await session.scalar(select(func.count()).select_from(ScheduledPost)) == 0
