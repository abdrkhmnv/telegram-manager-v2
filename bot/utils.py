"""Handlerlar uchun kichik yordamchilar."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram.types import Message

from bot.screens import Screen
from database.models import ChatType
from utils.time_utils import format_local

CHAT_TYPE_LABELS: dict[ChatType, str] = {
    ChatType.PRIVATE: "Shaxsiy chat",
    ChatType.GROUP: "Guruh",
    ChatType.SUPERGROUP: "Supergroup",
    ChatType.CHANNEL: "Kanal",
}


def h(value: object) -> str:
    """HTML uchun xavfsiz matn."""
    return escape(str(value))


async def reply(message: Message, screen: Screen) -> None:
    await message.answer(screen.text, reply_markup=screen.markup)


def when(value: object, tz: ZoneInfo) -> str:
    if isinstance(value, datetime):
        return format_local(value, tz)
    return "—"


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"  # pragma: no cover
