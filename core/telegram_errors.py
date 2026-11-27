"""Telegram (MTProto) chaqiruvlari uchun FloodWait'ni hurmat qiluvchi yordamchi."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from telethon.errors import FloodWaitError

from utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

DEFAULT_MAX_FLOOD_WAIT = 300
DEFAULT_FLOOD_RETRIES = 2


async def with_flood_wait(
    call: Callable[[], Awaitable[T]],
    *,
    max_wait: int = DEFAULT_MAX_FLOOD_WAIT,
    retries: int = DEFAULT_FLOOD_RETRIES,
    operation: str = "telegram",
) -> T:
    """``call()`` ni bajaradi; FloodWait bo'lsa Telegram aytgan muddatcha kutib qayta urinadi.

    * Kutish ``max_wait`` soniyadan uzun bo'lsa — kutilmaydi, xato yuqoriga uzatiladi
      (chaqiruvchi amalni keyinroqqa qoldirishi kerak).
    * Qayta urinishlar soni ``retries`` bilan cheklangan.
    * Telegram cheklovini chetlab o'tishga urinilmaydi — faqat aytilgan vaqt kutiladi.
    """
    if retries < 0 or max_wait < 0:
        raise ValueError("retries va max_wait manfiy bo'lmasligi kerak")
    attempt = 0
    while True:
        try:
            return await call()
        except FloodWaitError as exc:
            wait = int(getattr(exc, "seconds", 0) or 0)
            if wait > max_wait or attempt >= retries:
                logger.warning(
                    "FloodWait: amal bekor qilindi",
                    extra={"operation": operation, "wait": wait, "attempt": attempt},
                )
                raise
            attempt += 1
            logger.warning(
                "FloodWait: kutilmoqda",
                extra={"operation": operation, "wait": wait, "attempt": attempt},
            )
            await asyncio.sleep(wait + 1)


_ERROR_MESSAGES: dict[str, str] = {
    "ChatWriteForbiddenError": "Bu chatga yozish huquqi yo'q",
    "ChatAdminRequiredError": "Admin huquqi kerak",
    "ChannelPrivateError": "Kanal/guruh yopiq yoki akkaunt chiqarilgan",
    "UserIsBlockedError": "Foydalanuvchi akkauntni bloklagan",
    "UserBannedInChannelError": "Akkauntga bu chatda yozish taqiqlangan",
    "ChatForwardsRestrictedError": "Chat himoyalangan: forward/nusxalash taqiqlangan",
    "MessageIdInvalidError": "Xabar topilmadi",
    "MessageNotModifiedError": "Matn o'zgarmagan",
    "MessageEditTimeExpiredError": "Tahrirlash muddati o'tgan",
    "MessageAuthorRequiredError": "Faqat o'zingiz yuborgan xabarni o'zgartirish mumkin",
    "SlowModeWaitError": "Chatda sekin rejim yoqilgan",
    "MediaCaptionTooLongError": "Izoh juda uzun",
    "MessageTooLongError": "Xabar juda uzun",
    "PeerIdInvalidError": "Chat topilmadi — chatlar ro'yxatini yangilang",
}


def describe_error(exc: BaseException) -> str:
    """Telegram/tizim xatosini foydalanuvchiga tushunarli qisqa matnga aylantiradi."""
    name = type(exc).__name__
    if isinstance(exc, FloodWaitError):
        return f"Telegram cheklovi: {int(getattr(exc, 'seconds', 0))} soniya kutish kerak"
    if name in _ERROR_MESSAGES:
        return _ERROR_MESSAGES[name]
    if isinstance(exc, ValueError) and "entity" in str(exc).lower():
        return "Chat topilmadi — chatlar ro'yxatini yangilang"
    if isinstance(exc, FileNotFoundError):
        return "Media fayl diskda topilmadi"
    if isinstance(exc, ConnectionError | TimeoutError | OSError):
        return "Tarmoq xatosi, keyinroq qayta urinib ko'ring"
    return name
