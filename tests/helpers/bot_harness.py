"""Control Bot'ni tarmoqsiz sinash uchun yordamchilar (aiogram kerak)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update

from bot.context import Services
from bot.dispatcher import build_dispatcher

OWNER = 777
STRANGER = 999
BOT_ID = 123456
TOKEN = f"{BOT_ID}:FAKE-token-for-tests-0000000000000"
TASHKENT = ZoneInfo("Asia/Tashkent")


class RecordingSession(BaseSession):
    """Telegram'ga hech narsa yubormaydi, so'rovlarni yozib oladi va soxta javob qaytaradi."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self._next_id = 1000

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
        self.requests.append(method)
        if isinstance(method, SendMessage | EditMessageText):
            self._next_id += 1
            chat_id = getattr(method, "chat_id", None) or OWNER
            return Message(
                message_id=self._next_id,
                date=datetime.now(UTC),
                chat=Chat(id=int(chat_id), type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:
        return None

    def of(self, kind: type) -> list[Any]:
        return [r for r in self.requests if isinstance(r, kind)]


def make_services(**overrides: Any) -> Services:
    defaults: dict[str, Any] = {
        name: MagicMock()
        for name in ("status", "chats", "messages", "media", "rules", "autopost", "stats")
    }
    defaults["timezone"] = TASHKENT
    defaults.update(overrides)
    return Services(**defaults)


def make_bot(session: RecordingSession) -> Bot:
    return Bot(token=TOKEN, session=session)


def make_dispatcher(services: Services) -> Any:
    return build_dispatcher(owner_id=OWNER, storage=MemoryStorage(), services=services)


def user(user_id: int) -> dict[str, Any]:
    return {"id": user_id, "is_bot": False, "first_name": "U"}


_update_ids = iter(range(1, 10_000_000))


def message_update(
    user_id: int, text: str | None = None, *, chat_type: str = "private", **extra: Any
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": next(_update_ids),
        "date": 1_700_000_000,
        "chat": {"id": user_id if chat_type == "private" else -100, "type": chat_type},
        "from": user(user_id),
        **extra,
    }
    if text is not None:
        message["text"] = text
        if text.startswith("/"):
            message["entities"] = [
                {"type": "bot_command", "offset": 0, "length": len(text.split()[0])}
            ]
    return {"update_id": next(_update_ids), "message": message}


def callback_update(user_id: int, data: str) -> dict[str, Any]:
    update_id = next(_update_ids)
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


def async_mock(return_value: Any = None) -> AsyncMock:
    return AsyncMock(return_value=return_value)
