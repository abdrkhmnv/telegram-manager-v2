"""Control Bot testlari: haqiqiy Dispatcher orqali, tarmoqsiz (yozib oluvchi sessiya bilan)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("aiogram")
pytest.importorskip("sqlalchemy")
pytest.importorskip("telethon")

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Message

from bot import keyboards, screens, texts
from bot.callbacks import CALLBACK_DATA_LIMIT, NavCallback, Section
from bot.middleware.callback_guard import CallbackGuardMiddleware
from bot.rendering import show
from core.userbot import UserbotStatus
from services.status_service import SystemStatus
from tests.helpers.bot_harness import (
    OWNER,
    STRANGER,
    TASHKENT,
    RecordingSession,
    callback_update,
    feed,
    make_bot,
    make_dispatcher,
    make_services,
    message_update,
)

NOW = datetime(2026, 11, 27, 15, 0, tzinfo=UTC)


def make_status(*, authorized: bool = True) -> SystemStatus:
    return SystemStatus(
        version="1.0.0",
        started_at=NOW - timedelta(hours=2, minutes=5),
        checked_at=NOW,
        database_ok=True,
        migrations_current=True,
        migration_revision="0003",
        userbot=UserbotStatus(
            connected=authorized,
            authorized=authorized,
            user_id=OWNER if authorized else None,
            display_name="Ali <Admin>" if authorized else None,
            username="ali" if authorized else None,
        ),
        components={"forwarder": True, "scheduler": False},
    )


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return make_bot(session)


@pytest.fixture
def svc() -> Any:
    status = MagicMock()
    status.collect = AsyncMock(return_value=make_status())
    return make_services(status=status)


@pytest.fixture
def dispatcher(svc: Any) -> Any:
    return make_dispatcher(svc)


# ------------------------------------------------------------------ callbacks
class TestCallbackData:
    @pytest.mark.parametrize("section", list(Section))
    def test_every_section_fits_and_roundtrips(self, section: Section) -> None:
        packed = NavCallback(section=section, page=9999).pack()
        assert len(packed.encode()) <= CALLBACK_DATA_LIMIT
        assert NavCallback.unpack(packed).section is section

    def test_every_static_keyboard_button_is_valid(self) -> None:
        markups = [
            keyboards.main_menu(),
            keyboards.back_home(Section.SETTINGS),
            keyboards.settings_menu(),
            keyboards.status_menu(),
        ]
        for markup in markups:
            for row in markup.inline_keyboard:
                for button in row:
                    assert button.callback_data is not None
                    assert len(button.callback_data.encode()) <= CALLBACK_DATA_LIMIT
                    NavCallback.unpack(button.callback_data)


# ---------------------------------------------------------------- dashboard
class TestDashboard:
    def test_main_menu_has_all_sections_in_uzbek(self) -> None:
        markup = keyboards.main_menu()
        labels = [button.text for row in markup.inline_keyboard for button in row]
        assert labels == [
            "📤 Xabar yuborish",
            "🔁 Forwarder",
            "📅 Autopost",
            "🎲 Random Autopost",
            "🖼 Media Manager",
            "💬 Chatlar",
            "👥 Guruhlar",
            "📢 Kanallar",
            "🔎 Qidiruv",
            "📊 Statistika",
            "⚙️ Sozlamalar",
            "❓ Yordam",
        ]
        assert all(len(row) <= 2 for row in markup.inline_keyboard)

    def test_status_screen_escapes_and_formats(self) -> None:
        screen = screens.status_screen(make_status(), TASHKENT)
        assert "Ali &lt;Admin&gt; (@ali)" in screen.text
        assert "27.11.2026 20:00" in screen.text
        assert "2 soat 5 daqiqa" in screen.text
        assert "✅ PostgreSQL" in screen.text
        assert "✅ Forwarder" in screen.text
        assert "❌ Rejalashtiruvchi" in screen.text

    def test_status_screen_when_userbot_offline(self) -> None:
        screen = screens.status_screen(make_status(authorized=False), TASHKENT)
        assert "❌ Userbot: ulanmagan" in screen.text

    def test_every_main_section_has_a_real_handler(self) -> None:
        assert texts.PLANNED_PHASE == {}


# ----------------------------------------------------- end-to-end dispatch
class TestDispatch:
    async def test_owner_start_gets_main_menu(
        self, dispatcher: Any, bot: Bot, session: RecordingSession
    ) -> None:
        await feed(dispatcher, bot, message_update(OWNER, "/start"))
        messages = session.of(SendMessage)
        assert len(messages) == 1
        assert messages[0].chat_id == OWNER
        assert "Telegram Manager v2" in messages[0].text
        assert messages[0].reply_markup == keyboards.main_menu()

    async def test_owner_help(self, dispatcher: Any, bot: Bot, session: RecordingSession) -> None:
        await feed(dispatcher, bot, message_update(OWNER, "/help"))
        assert "Yordam" in session.of(SendMessage)[0].text

    @pytest.mark.parametrize(
        "payload",
        [
            message_update(STRANGER, "/start"),
            callback_update(STRANGER, NavCallback(section=Section.STATUS).pack()),
            callback_update(STRANGER, NavCallback(section=Section.CHATS).pack()),
            message_update(OWNER, "/start", chat_type="group"),
        ],
        ids=["stranger-message", "stranger-status", "stranger-chats", "owner-in-group"],
    )
    async def test_everyone_else_is_ignored(
        self, dispatcher: Any, bot: Bot, session: RecordingSession, svc: Any, payload: Any
    ) -> None:
        await feed(dispatcher, bot, payload)
        assert session.requests == []
        svc.status.collect.assert_not_awaited()

    async def test_navigation_edits_existing_message(
        self, dispatcher: Any, bot: Bot, session: RecordingSession
    ) -> None:
        await feed(
            dispatcher, bot, callback_update(OWNER, NavCallback(section=Section.HELP).pack())
        )
        edits = session.of(EditMessageText)
        assert len(edits) == 1
        assert edits[0].message_id == 20
        assert "Yordam" in edits[0].text
        assert session.of(SendMessage) == []
        assert len(session.of(AnswerCallbackQuery)) == 1

    async def test_status_shows_loading_then_status(
        self, dispatcher: Any, bot: Bot, session: RecordingSession, svc: Any
    ) -> None:
        await feed(
            dispatcher, bot, callback_update(OWNER, NavCallback(section=Section.STATUS).pack())
        )
        svc.status.collect.assert_awaited_once()
        answers = session.of(AnswerCallbackQuery)
        assert len(answers) == 1 and answers[0].text == "Tekshirilmoqda…"
        assert "Tizim holati" in session.of(EditMessageText)[0].text

    @pytest.mark.parametrize("data", ["nav:unknown:0", "legacy_button", "nav:help:notanint"])
    async def test_expired_or_invalid_callback_returns_home(
        self, dispatcher: Any, bot: Bot, session: RecordingSession, data: str
    ) -> None:
        await feed(dispatcher, bot, callback_update(OWNER, data))
        assert session.of(AnswerCallbackQuery)[0].text == texts.EXPIRED_CALLBACK
        assert "Telegram Manager v2" in session.of(EditMessageText)[0].text

    async def test_flow_button_without_flow_is_treated_as_expired(
        self, dispatcher: Any, bot: Bot, session: RecordingSession, svc: Any
    ) -> None:
        # Yuborish tugmasi holat (FSM) yo'q paytda bosilsa — hech narsa yuborilmaydi.
        await feed(dispatcher, bot, callback_update(OWNER, "fl:send:"))
        assert session.of(AnswerCallbackQuery)[0].text == texts.EXPIRED_CALLBACK
        svc.messages.send.assert_not_called()

    async def test_unknown_text(self, dispatcher: Any, bot: Bot, session: RecordingSession) -> None:
        await feed(dispatcher, bot, message_update(OWNER, "salom"))
        assert session.of(SendMessage)[0].text == texts.UNKNOWN_MESSAGE


# ------------------------------------------------------------- rendering
def fake_callback(edit_side_effect: Exception | None = None) -> MagicMock:
    message = MagicMock(spec=Message)
    message.edit_text = AsyncMock(side_effect=edit_side_effect)
    message.answer = AsyncMock()
    callback = MagicMock(spec=CallbackQuery)
    callback.message = message
    return callback


class TestRendering:
    async def test_not_modified_is_silent(self) -> None:
        error = TelegramBadRequest(
            method=MagicMock(), message="Bad Request: message is not modified"
        )
        callback = fake_callback(error)
        await show(callback, screens.main_menu())
        callback.message.answer.assert_not_awaited()

    async def test_uneditable_message_falls_back_to_new_message(self) -> None:
        error = TelegramBadRequest(
            method=MagicMock(), message="Bad Request: message can't be edited"
        )
        callback = fake_callback(error)
        await show(callback, screens.main_menu())
        callback.message.answer.assert_awaited_once()


# ---------------------------------------------------------- callback guard
class TestCallbackGuard:
    @staticmethod
    def make_query(data: str = "nav:help:0") -> MagicMock:
        query = MagicMock(spec=CallbackQuery)
        query.from_user = MagicMock(id=OWNER)
        query.data = data
        query.answer = AsyncMock()
        return query

    async def test_double_tap_is_ignored(self) -> None:
        clock = iter([0.0, 0.3, 5.0])
        guard = CallbackGuardMiddleware(window=1.0, clock=lambda: next(clock))
        handler = AsyncMock(return_value="done")
        query = self.make_query()
        assert await guard(handler, query, {}) == "done"
        assert await guard(handler, query, {}) is None
        assert await guard(handler, query, {}) == "done"
        assert handler.await_count == 2

    async def test_concurrent_callbacks_are_serialized(self) -> None:
        guard = CallbackGuardMiddleware()
        release = asyncio.Event()

        async def slow_handler(event: Any, data: dict[str, Any]) -> str:
            await release.wait()
            return "slow"

        first = asyncio.create_task(guard(slow_handler, self.make_query("a"), {}))
        await asyncio.sleep(0)
        busy_query = self.make_query("b")
        assert await guard(AsyncMock(), busy_query, {}) is None
        busy_query.answer.assert_awaited_once_with(texts.BUSY)
        release.set()
        assert await first == "slow"

    async def test_non_callback_events_pass_through(self) -> None:
        handler = AsyncMock(return_value="ok")
        assert await CallbackGuardMiddleware()(handler, MagicMock(), {}) == "ok"
