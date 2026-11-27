"""Panel oqimlarini real Dispatcher orqali boshidan oxirigacha sinash (soxta servislar bilan)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("aiogram")
pytest.importorskip("sqlalchemy")
pytest.importorskip("telethon")

from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from database.models import (
    AutopostKind,
    ChatType,
    ForwardMode,
    Recurrence,
    RuleStatus,
    TaskStatus,
)
from services.chat_service import ChatPage
from services.message_service import DeliveryResult, OutgoingContent, SendReport
from services.statistics_service import Statistics, Totals
from tests.helpers.bot_harness import (
    OWNER,
    RecordingSession,
    callback_update,
    feed,
    make_bot,
    make_dispatcher,
    make_services,
    message_update,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


def chat(chat_id: int, title: str, chat_type: ChatType = ChatType.CHANNEL) -> SimpleNamespace:
    return SimpleNamespace(
        id=chat_id,
        telegram_id=-1000000000000 - chat_id,
        title=title,
        chat_type=chat_type,
        is_saved=False,
        is_accessible=True,
        username=None,
        members_count=None,
        last_synced_at=NOW,
    )


CHATS = [chat(1, "Manba kanal"), chat(2, "Manzil kanal"), chat(3, "Guruh", ChatType.GROUP)]


def chat_services() -> Any:
    chats = MagicMock()
    chats.page = AsyncMock(return_value=ChatPage(chats=CHATS, total=3, page=0, pages=1))
    chats.sync_dialogs = AsyncMock(return_value=SimpleNamespace(total=3))
    return chats


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return make_bot(session)


async def run(dispatcher: Any, bot: Bot, *payloads: dict[str, Any]) -> None:
    for payload in payloads:
        await feed(dispatcher, bot, payload)


def texts_of(session: RecordingSession) -> str:
    return "\n".join(
        str(getattr(r, "text", "") or "")
        for r in session.of(SendMessage) + session.of(EditMessageText)
    )


# ------------------------------------------------------------------- send
async def test_send_flow_previews_confirms_and_sends_once(
    bot: Bot, session: RecordingSession
) -> None:
    messages = MagicMock()
    messages.destinations = AsyncMock(return_value=[CHATS[1]])
    messages.send = AsyncMock(
        return_value=SendReport([DeliveryResult(2, CHATS[1].telegram_id, "Manzil kanal", True, 55)])
    )
    media = MagicMock()
    media.get_many = AsyncMock(return_value=[])
    svc = make_services(chats=chat_services(), messages=messages, media=media)
    dispatcher = make_dispatcher(svc)

    await run(
        dispatcher,
        bot,
        callback_update(OWNER, "nav:send:0"),
        callback_update(OWNER, "pk:t:2:0"),
        callback_update(OWNER, "pk:d:0:0"),
        message_update(OWNER, "Salom dunyo"),
        callback_update(OWNER, "fl:preview:"),
    )
    # Oldindan ko'rish egasiga yuborildi, yuborish hali boshlanmadi.
    assert any(getattr(r, "text", None) == "Salom dunyo" for r in session.of(SendMessage))
    messages.send.assert_not_called()
    assert "1 ta chatga yuborilsinmi" in texts_of(session)

    await run(dispatcher, bot, callback_update(OWNER, "fl:send:"))
    messages.send.assert_awaited_once()
    content, picked = messages.send.await_args.args
    assert content == OutgoingContent(text="Salom dunyo", media=())
    assert picked == [2]
    assert "✅ 1 ta yuborildi" in texts_of(session)

    # Tasdiqlash tugmasi qayta bosilsa — ikkinchi marta yuborilmaydi.
    await run(dispatcher, bot, callback_update(OWNER, "fl:send:x"))
    assert messages.send.await_count == 1


async def test_picker_requires_selection(bot: Bot, session: RecordingSession) -> None:
    svc = make_services(chats=chat_services())
    dispatcher = make_dispatcher(svc)
    await run(
        dispatcher, bot, callback_update(OWNER, "nav:send:0"), callback_update(OWNER, "pk:d:0:0")
    )
    alerts = [a for a in session.of(AnswerCallbackQuery) if a.show_alert]
    assert alerts and "Kamida bitta chat" in (alerts[0].text or "")


# --------------------------------------------------------------- forwarder
async def test_forward_rule_wizard_blocks_loops_and_creates_rule(
    bot: Bot, session: RecordingSession
) -> None:
    created = SimpleNamespace(
        id=9,
        name="Test qoida",
        status=RuleStatus.ACTIVE,
        mode=ForwardMode.COPY,
        sources=[CHATS[0]],
        destinations=[CHATS[1]],
        include_keywords=[],
        exclude_keywords=[],
        media_types=[],
        duplicate_detection=False,
        header_text=None,
        footer_text=None,
    )
    rules = MagicMock()
    rules.create = AsyncMock(return_value=created)
    rules.get = AsyncMock(return_value=created)
    rules.counts_last_day = AsyncMock(return_value={})
    svc = make_services(chats=chat_services(), rules=rules)
    dispatcher = make_dispatcher(svc)

    await run(
        dispatcher,
        bot,
        callback_update(OWNER, "fl:fr_new:"),
        message_update(OWNER, "Test qoida"),
        callback_update(OWNER, "fl:fr_mode:copy"),
        callback_update(OWNER, "pk:t:1:0"),
        callback_update(OWNER, "pk:d:0:0"),
        callback_update(OWNER, "pk:t:1:1"),  # manzil sifatida ham o'sha chat
        callback_update(OWNER, "pk:d:0:1"),
    )
    rules.create.assert_not_called()
    assert any(a.show_alert for a in session.of(AnswerCallbackQuery))

    # Har bir tugma ma'lumoti noyob: callback himoyasi 1 soniyada takroriy bosishni o'tkazmaydi.
    await run(
        dispatcher,
        bot,
        callback_update(OWNER, "pk:t:1:2"),
        callback_update(OWNER, "pk:t:2:2"),
        callback_update(OWNER, "pk:d:0:2"),
    )
    rules.create.assert_awaited_once_with("Test qoida", ForwardMode.COPY, [1], [2])
    assert "Test qoida" in texts_of(session)
    assert "Copy (nusxa)" in texts_of(session)


async def test_keyword_filters_are_parsed(bot: Bot, session: RecordingSession) -> None:
    rule = SimpleNamespace(
        id=4,
        name="R",
        status=RuleStatus.ACTIVE,
        mode=ForwardMode.NATIVE,
        sources=[],
        destinations=[],
        include_keywords=[],
        exclude_keywords=[],
        media_types=[],
        duplicate_detection=False,
        header_text=None,
        footer_text=None,
    )
    rules = MagicMock()
    rules.get = AsyncMock(return_value=rule)
    rules.update = AsyncMock(return_value=True)
    rules.counts_last_day = AsyncMock(return_value={})
    dispatcher = make_dispatcher(make_services(rules=rules))
    await run(
        dispatcher,
        bot,
        callback_update(OWNER, "fr:k:4:"),
        message_update(OWNER, "+aksiya, Chegirma\n-reklama"),
    )
    rules.update.assert_awaited_once_with(
        4, include_keywords=["aksiya", "Chegirma"], exclude_keywords=["reklama"]
    )


# ---------------------------------------------------------------- autopost
def task_like(kind: AutopostKind) -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        name="Post: test",
        kind=kind,
        status=TaskStatus.ACTIVE,
        recurrence=Recurrence.DAILY if kind is AutopostKind.SCHEDULED else None,
        time_of_day=time(9, 30),
        weekdays_mask=None,
        next_run_at=NOW,
        last_run_at=None,
        destinations=[CHATS[2]],
        template_id=None,
        consecutive_failures=0,
        min_interval_seconds=1800,
        max_interval_seconds=5400,
        active_from=time(9, 0),
        active_to=time(22, 0),
    )


def autopost_services(kind: AutopostKind) -> Any:
    autopost = MagicMock()
    task = task_like(kind)
    autopost.create_scheduled = AsyncMock(return_value=task)
    autopost.create_random = AsyncMock(return_value=task)
    autopost.get = AsyncMock(return_value=task)
    autopost.template = AsyncMock(return_value=None)
    autopost.stats = AsyncMock(return_value={})
    autopost.queue = AsyncMock(return_value=[])
    return autopost


async def test_daily_autopost_wizard(bot: Bot, session: RecordingSession) -> None:
    autopost = autopost_services(AutopostKind.SCHEDULED)
    dispatcher = make_dispatcher(make_services(chats=chat_services(), autopost=autopost))
    await run(
        dispatcher,
        bot,
        callback_update(OWNER, "fl:ap_new:"),
        message_update(OWNER, "Kunlik post"),
        callback_update(OWNER, "fl:ap_next:"),
        callback_update(OWNER, "pk:t:3:0"),
        callback_update(OWNER, "pk:d:0:0"),
        callback_update(OWNER, "fl:ap_rec:daily"),
        message_update(OWNER, "25:99"),  # noto'g'ri vaqt — qayta so'raladi
        message_update(OWNER, "09:30"),
    )
    autopost.create_scheduled.assert_awaited_once()
    call = autopost.create_scheduled.await_args
    assert call.args[0].text == "Kunlik post"
    assert call.args[1] == [3]
    assert call.kwargs["recurrence"] is Recurrence.DAILY
    assert call.kwargs["at"] == time(9, 30)
    assert "Vaqt formati" in texts_of(session)
    assert "Post rejalashtirildi" in texts_of(session)


async def test_random_autopost_wizard(bot: Bot, session: RecordingSession) -> None:
    autopost = autopost_services(AutopostKind.RANDOM)
    dispatcher = make_dispatcher(make_services(chats=chat_services(), autopost=autopost))
    await run(
        dispatcher,
        bot,
        callback_update(OWNER, "fl:rp_new:"),
        callback_update(OWNER, "pk:t:3:0"),
        callback_update(OWNER, "pk:d:0:0"),
        message_update(OWNER, "30-90"),
        message_update(OWNER, "09:00-22:00"),
        message_update(OWNER, "Birinchi post"),
        message_update(OWNER, "Ikkinchi post"),
        callback_update(OWNER, "fl:rp_save:"),
    )
    autopost.create_random.assert_awaited_once()
    call = autopost.create_random.await_args
    assert [p.text for p in call.args[0]] == ["Birinchi post", "Ikkinchi post"]
    assert call.kwargs["min_seconds"] == 1800 and call.kwargs["max_seconds"] == 5400
    assert call.kwargs["active_from"] == time(9, 0) and call.kwargs["active_to"] == time(22, 0)


# ------------------------------------------------------------ chats & stats
async def test_chat_list_and_sync(bot: Bot, session: RecordingSession) -> None:
    chats = chat_services()
    dispatcher = make_dispatcher(make_services(chats=chats))
    await run(dispatcher, bot, callback_update(OWNER, "nav:groups:0"))
    chats.page.assert_awaited_with((ChatType.GROUP, ChatType.SUPERGROUP), 0)
    await run(dispatcher, bot, callback_update(OWNER, "ch:y:0:groups:0:0"))
    chats.sync_dialogs.assert_awaited_once()
    assert "Yangilandi: 3 ta dialog" in texts_of(session)


async def test_statistics_screen(bot: Bot, session: RecordingSession) -> None:
    totals = Totals(
        messages_sent=5,
        native_forwards=3,
        copy_deliveries=2,
        scheduled_posts=1,
        random_posts=4,
        failed=1,
    )
    stats = MagicMock()
    stats.collect = AsyncMock(
        return_value=Statistics(
            all_time=totals,
            today=totals,
            active_tasks=2,
            paused_tasks=1,
            active_rules=1,
            paused_rules=0,
            daily=[(date(2026, 11, 21 + i), i) for i in range(7)],
        )
    )
    dispatcher = make_dispatcher(make_services(stats=stats))
    await run(dispatcher, bot, callback_update(OWNER, "nav:stats:0"))
    text = texts_of(session)
    assert "📊 Statistika" in text
    assert "Muvaffaqiyatli: 15" in text
    assert "21 ta muvaffaqiyatli amal" in text
