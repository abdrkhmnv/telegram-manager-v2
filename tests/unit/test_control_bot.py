"""Control Bot testlari: haqiqiy Dispatcher orqali, tarmoqsiz (yozib oluvchi sessiya bilan)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("aiogram")
pytest.importorskip("sqlalchemy")

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Message, Update

from bot import keyboards, screens, texts
from bot.callbacks import CALLBACK_DATA_LIMIT, NavCallback, Section
from bot.dispatcher import build_dispatcher
from bot.middleware.callback_guard import CallbackGuardMiddleware
from bot.rendering import show
from core.userbot import UserbotStatus
from services.status_service import SystemStatus

OWNER = 777
STRANGER = 999
BOT_ID = 123456
TOKEN = f"{BOT_ID}:FAKE-token-for-tests-0000000000000"
TASHKENT = ZoneInfo("Asia/Tashkent")
NOW = datetime(2026, 11, 27, 15, 0, tzinfo=UTC)


class RecordingSession(BaseSession):
    """Telegram'ga hech narsa yubormaydi, faqat so'rovlarni yozib oladi."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
        self.requests.append(method)
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:
        return None


def make_status(*, authorized: bool = True) -> SystemStatus:
    return SystemStatus(
        version="0.2.0",
        started_at=NOW - timedelta(hours=2, minutes=5),
        checked_at=NOW,
        database_ok=True,
        migrations_current=True,
        migration_revision="0002",
        userbot=UserbotStatus(
            connected=authorized,
            authorized=authorized,
            user_id=OWNER if authorized else None,
            display_name="Ali <Admin>" if authorized else None,
            username="ali" if authorized else None,
        ),
    )


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return Bot(token=TOKEN, session=session)


@pytest.fixture
def status_service() -> MagicMock:
    service = MagicMock()
    service.collect = AsyncMock(return_value=make_status())
    return service


@pytest.fixture
def dispatcher(status_service: MagicMock) -> Any:
    return build_dispatcher(
        owner_id=OWNER, storage=MemoryStorage(), status_service=status_service, timezone=TASHKENT
    )


def user(user_id: int) -> dict[str, Any]:
    return {"id": user_id, "is_bot": False, "first_name": "U"}


def message_update(
    user_id: int, text: str, *, chat_type: str = "private", update_id: int = 1
) -> dict[str, Any]:
    entities = (
        [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        if text.startswith("/")
        else []
    )
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "date": 1_700_000_000,
            "chat": {"id": user_id if chat_type == "private" else -100, "type": chat_type},
            "from": user(user_id),
            "text": text,
            "entities": entities,
        },
    }


def callback_update(user_id: int, data: str, *, update_id: int = 2) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "from": user(user_id),
            "chat_instance": "ci",
            "data": data,
            "message": {
                "message_id": 20,
                "date": 1_700_000_000,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": BOT_ID, "is_bot": True, "first_name": "Bot"},
                "text": "panel",
            },
        },
    }


async def feed(dispatcher: Any, bot: Bot, payload: dict[str, Any]) -> None:
    update = Update.model_validate(payload, context={"bot": bot})
    await dispatcher.feed_update(bot, update)


def sent(session: RecordingSession, kind: type) -> list[Any]:
    return [r for r in session.requests if isinstance(r, kind)]


# ------------------------------------------------------------------ callbacks
class TestCallbackData:
    @pytest.mark.parametrize("section", list(Section))
    def test_every_section_fits_and_roundtrips(self, section: Section) -> None:
        packed = NavCallback(section=section, page=9999).pack()
        assert len(packed.encode()) <= CALLBACK_DATA_LIMIT
        assert NavCallback.unpack(packed).section is section

    def test_every_keyboard_button_is_valid(self) -> None:
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

    def test_status_screen_when_userbot_offline(self) -> None:
        screen = screens.status_screen(make_status(authorized=False), TASHKENT)
        assert "❌ Userbot: ulanmagan" in screen.text

    @pytest.mark.parametrize("section", [s for s in texts.PLANNED_PHASE])
    def test_unimplemented_sections_say_which_phase(self, section: Section) -> None:
        screen = screens.coming_soon(section)
        assert f"{texts.PLANNED_PHASE[section]}-bosqichda" in screen.text


# ----------------------------------------------------- end-to-end dispatch
class TestDispatch:
    async def test_owner_start_gets_main_menu(
        self, dispatcher: Any, bot: Bot, session: RecordingSession
    ) -> None:
        await feed(dispatcher, bot, message_update(OWNER, "/start"))
        messages = sent(session, SendMessage)
        assert len(messages) == 1
        assert messages[0].chat_id == OWNER
        assert "Telegram Manager v2" in messages[0].text
        assert messages[0].reply_markup == keyboards.main_menu()

    async def test_owner_help(self, dispatcher: Any, bot: Bot, session: RecordingSession) -> None:
        await feed(dispatcher, bot, message_update(OWNER, "/help"))
        assert "Yordam" in sent(session, SendMessage)[0].text

    @pytest.mark.parametrize(
        "payload",
        [
            message_update(STRANGER, "/start"),
            callback_update(STRANGER, NavCallback(section=Section.STATUS).pack()),
            message_update(OWNER, "/start", chat_type="group"),
        ],
        ids=["stranger-message", "stranger-callback", "owner-in-group"],
    )
    async def test_everyone_else_is_ignored(
        self,
        dispatcher: Any,
        bot: Bot,
        session: RecordingSession,
        status_service: MagicMock,
        payload: dict[str, Any],
    ) -> None:
        await feed(dispatcher, bot, payload)
        assert session.requests == []
        status_service.collect.assert_not_awaited()

    async def test_navigation_edits_existing_message(
        self, dispatcher: Any, bot: Bot, session: RecordingSession
    ) -> None:
        await feed(
            dispatcher, bot, callback_update(OWNER, NavCallback(section=Section.HELP).pack())
        )
        edits = sent(session, EditMessageText)
        assert len(edits) == 1
        assert edits[0].message_id == 20
        assert "Yordam" in edits[0].text
        assert sent(session, SendMessage) == []
        assert len(sent(session, AnswerCallbackQuery)) == 1

    async def test_status_shows_loading_then_status(
        self, dispatcher: Any, bot: Bot, session: RecordingSession, status_service: MagicMock
    ) -> None:
        await feed(
            dispatcher, bot, callback_update(OWNER, NavCallback(section=Section.STATUS).pack())
        )
        status_service.collect.assert_awaited_once()
        answers = sent(session, AnswerCallbackQuery)
        assert len(answers) == 1 and answers[0].text == "Tekshirilmoqda…"
        assert "Tizim holati" in sent(session, EditMessageText)[0].text

    @pytest.mark.parametrize("data", ["nav:unknown:0", "legacy_button", "nav:help:notanint"])
    async def test_expired_or_invalid_callback_returns_home(
        self, dispatcher: Any, bot: Bot, session: RecordingSession, data: str
    ) -> None:
        await feed(dispatcher, bot, callback_update(OWNER, data))
        assert sent(session, AnswerCallbackQuery)[0].text == texts.EXPIRED_CALLBACK
        assert "Telegram Manager v2" in sent(session, EditMessageText)[0].text

    async def test_unknown_text(self, dispatcher: Any, bot: Bot, session: RecordingSession) -> None:
        await feed(dispatcher, bot, message_update(OWNER, "salom"))
        assert sent(session, SendMessage)[0].text == texts.UNKNOWN_MESSAGE


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
        import asyncio

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
