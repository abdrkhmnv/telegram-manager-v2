"""Ekranni ko'rsatish: mavjud panel xabarini tahrirlash, iloji bo'lmasa yangisini yuborish."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from bot.screens import Screen
from utils.logger import get_logger

logger = get_logger(__name__)

_NOT_MODIFIED = "message is not modified"


async def show(callback: CallbackQuery, screen: Screen) -> None:
    """Chatni to'ldirib yubormaslik uchun eski xabar tahrirlanadi."""
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(screen.text, reply_markup=screen.markup)
            return
        except TelegramBadRequest as exc:
            if _NOT_MODIFIED in str(exc).lower():
                return
            logger.info("Panel xabarini tahrirlab bo'lmadi, yangisi yuboriladi")
        await message.answer(screen.text, reply_markup=screen.markup)
        return
    if callback.bot is not None:
        await callback.bot.send_message(
            callback.from_user.id, screen.text, reply_markup=screen.markup
        )
