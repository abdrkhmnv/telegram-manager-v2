"""Autopost va Random Autopost uchun umumiy belgilar va yordamchilar."""

from __future__ import annotations

from pathlib import Path

from aiogram import Bot

from bot.content import send_stored_preview
from bot.context import Services
from database.models import MediaType, TaskStatus
from services.media_service import MediaMissingError

TASK_ICONS = {
    TaskStatus.ACTIVE: "🟢",
    TaskStatus.PAUSED: "⏸",
    TaskStatus.COMPLETED: "✅",
    TaskStatus.CANCELLED: "🚫",
    TaskStatus.FAILED: "❌",
}
TASK_LABELS = {
    TaskStatus.ACTIVE: "faol",
    TaskStatus.PAUSED: "pauzada",
    TaskStatus.COMPLETED: "bajarildi",
    TaskStatus.CANCELLED: "bekor qilingan",
    TaskStatus.FAILED: "xato bilan tugadi",
}


async def preview_template(bot: Bot, chat_id: int, svc: Services, template_id: int) -> None:
    template = await svc.autopost.template(template_id)
    if template is None:
        await bot.send_message(chat_id, "Post topilmadi.")
        return
    items: list[tuple[Path, MediaType]] = []
    for item in sorted(template.media_items, key=lambda i: i.position):
        try:
            items.append((await svc.media.path_for(item.media), item.media.media_type))
        except MediaMissingError:
            await bot.send_message(chat_id, "⚠️ Postdagi media fayl diskda topilmadi.")
            return
    await send_stored_preview(bot, chat_id, template.text, items)
