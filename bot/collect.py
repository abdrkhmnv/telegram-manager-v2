"""Bir yoki bir nechta xabardan kontent yig'ish (matn + albom).

Xabar yuborish va post shablonlari uchun ishlatiladi.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message

from bot.content import incoming_media, message_html
from bot.context import Services
from database.models import MediaType
from services.media_service import check_album
from services.message_service import OutgoingContent
from utils.validators import (
    TELEGRAM_CAPTION_LIMIT,
    TELEGRAM_MESSAGE_LIMIT,
    InputValidationError,
)

KIND_LABELS = {
    MediaType.PHOTO: "rasm",
    MediaType.VIDEO: "video",
    MediaType.ANIMATION: "GIF",
    MediaType.DOCUMENT: "hujjat",
    MediaType.AUDIO: "audio",
    MediaType.VOICE: "ovozli xabar",
}


async def collect(message: Message, bot: Bot, svc: Services, state: FSMContext) -> str | None:
    """Xabarni FSM ``text``/``media`` ga qo'shadi. Qaytaradi: xato matni yoki ``None``."""
    data = await state.get_data()
    media: list[dict[str, Any]] = list(data.get("media", []))
    text: str | None = data.get("text")
    found = incoming_media(message)
    html_text = message_html(message)
    if found is None and html_text is None:
        return "Bu turdagi xabar qo'llab-quvvatlanmaydi. Matn yoki media yuboring."
    if found is not None:
        try:
            check_album([MediaType(m["t"]) for m in media] + [found.media_type])
            stored = await svc.media.store_from_bot(bot, found)
        except InputValidationError as exc:
            return str(exc)
        media.append({"id": stored.id, "fid": found.file_id, "t": found.media_type.value})
    if html_text is not None:
        text = html_text
    limit = TELEGRAM_CAPTION_LIMIT if media else TELEGRAM_MESSAGE_LIMIT
    if text and len(text) > limit:
        return f"Matn juda uzun: {len(text)} belgi (ko'pi bilan {limit}, media bilan 1024)."
    await state.update_data(text=text, media=media)
    return None


async def collected(svc: Services, state: FSMContext) -> OutgoingContent:
    data = await state.get_data()
    media_items = await svc.media.get_many([int(m["id"]) for m in data.get("media", [])])
    return OutgoingContent(text=data.get("text"), media=tuple(media_items))


async def summary(state: FSMContext) -> str:
    data = await state.get_data()
    parts = []
    if data.get("text"):
        parts.append("✅ matn")
    counts: dict[str, int] = {}
    for item in data.get("media", []):
        label = KIND_LABELS[MediaType(item["t"])]
        counts[label] = counts.get(label, 0) + 1
    parts.extend(f"✅ {n} ta {label}" for label, n in counts.items())
    return ", ".join(parts) or "hali hech narsa"


async def upsert_status(
    message: Message, bot: Bot, state: FSMContext, text: str, reply_markup: InlineKeyboardMarkup
) -> None:
    """Holat xabarini tahrirlaydi (albom kelganda chat to'lib ketmasligi uchun)."""
    data = await state.get_data()
    status_id = data.get("status_msg_id")
    if status_id:
        try:
            await bot.edit_message_text(
                text, chat_id=message.chat.id, message_id=status_id, reply_markup=reply_markup
            )
            return
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                return
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(status_msg_id=sent.message_id)
