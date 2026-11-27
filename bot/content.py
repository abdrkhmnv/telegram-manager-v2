"""Egasi botga yuborgan kontentni qabul qilish va oldindan ko'rsatish."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.types import (
    FSInputFile,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from database.models import MediaType
from services.media_service import IncomingMedia


def incoming_media(message: Message) -> IncomingMedia | None:
    """Xabardagi media haqida ma'lumot (animation hujjatdan oldin tekshiriladi)."""
    if message.photo:
        photo = message.photo[-1]
        return IncomingMedia(
            photo.file_id,
            MediaType.PHOTO,
            "image/jpeg",
            photo.file_size,
            width=photo.width,
            height=photo.height,
        )
    if message.animation:
        a = message.animation
        return IncomingMedia(
            a.file_id,
            MediaType.ANIMATION,
            a.mime_type or "video/mp4",
            a.file_size,
            a.file_name,
            a.width,
            a.height,
            a.duration,
        )
    if message.video:
        v = message.video
        return IncomingMedia(
            v.file_id,
            MediaType.VIDEO,
            v.mime_type or "video/mp4",
            v.file_size,
            v.file_name,
            v.width,
            v.height,
            v.duration,
        )
    if message.voice:
        vo = message.voice
        return IncomingMedia(
            vo.file_id,
            MediaType.VOICE,
            vo.mime_type or "audio/ogg",
            vo.file_size,
            duration=vo.duration,
        )
    if message.audio:
        au = message.audio
        return IncomingMedia(
            au.file_id,
            MediaType.AUDIO,
            au.mime_type or "audio/mpeg",
            au.file_size,
            au.file_name,
            duration=au.duration,
        )
    if message.document:
        d = message.document
        return IncomingMedia(
            d.file_id,
            MediaType.DOCUMENT,
            d.mime_type or "application/octet-stream",
            d.file_size,
            d.file_name,
        )
    return None


def message_html(message: Message) -> str | None:
    """Matn yoki izohni Telegram formatlash (HTML) bilan qaytaradi."""
    if not (message.text or message.caption):
        return None
    return message.html_text


async def send_preview(
    bot: Bot, chat_id: int, text: str | None, media: list[dict[str, Any]]
) -> None:
    """Kontentni botning o'zi orqali egasiga ko'rsatadi (file_id bo'yicha, qayta yuklamasdan)."""
    if not media:
        await bot.send_message(chat_id, text or "—")
        return
    if len(media) == 1:
        item = media[0]
        fid, kind = item["fid"], MediaType(item["t"])
        senders: dict[MediaType, Callable[..., Awaitable[Any]]] = {
            MediaType.PHOTO: bot.send_photo,
            MediaType.VIDEO: bot.send_video,
            MediaType.ANIMATION: bot.send_animation,
            MediaType.DOCUMENT: bot.send_document,
            MediaType.AUDIO: bot.send_audio,
            MediaType.VOICE: bot.send_voice,
        }
        await senders[kind](chat_id, fid, caption=text)
        return
    group: list[Any] = []
    for index, item in enumerate(media):
        caption = text if index == 0 else None
        kind = MediaType(item["t"])
        if kind is MediaType.PHOTO:
            group.append(InputMediaPhoto(media=item["fid"], caption=caption))
        elif kind is MediaType.VIDEO:
            group.append(InputMediaVideo(media=item["fid"], caption=caption))
        elif kind is MediaType.AUDIO:
            group.append(InputMediaAudio(media=item["fid"], caption=caption))
        else:
            group.append(InputMediaDocument(media=item["fid"], caption=caption))
    await bot.send_media_group(chat_id, group)


async def send_stored_preview(
    bot: Bot, chat_id: int, text: str | None, items: list[tuple[Path, MediaType]]
) -> None:
    """Diskda saqlangan post (shablon) ko'rinishini egasiga yuboradi."""
    if not items:
        await bot.send_message(chat_id, text or "—")
        return
    if len(items) == 1:
        path, kind = items[0]
        senders: dict[MediaType, Callable[..., Awaitable[Any]]] = {
            MediaType.PHOTO: bot.send_photo,
            MediaType.VIDEO: bot.send_video,
            MediaType.ANIMATION: bot.send_animation,
            MediaType.DOCUMENT: bot.send_document,
            MediaType.AUDIO: bot.send_audio,
            MediaType.VOICE: bot.send_voice,
        }
        await senders[kind](chat_id, FSInputFile(path), caption=text)
        return
    group: list[Any] = []
    for index, (path, kind) in enumerate(items):
        caption = text if index == 0 else None
        media = FSInputFile(path)
        if kind is MediaType.PHOTO:
            group.append(InputMediaPhoto(media=media, caption=caption))
        elif kind is MediaType.VIDEO:
            group.append(InputMediaVideo(media=media, caption=caption))
        elif kind is MediaType.AUDIO:
            group.append(InputMediaAudio(media=media, caption=caption))
        else:
            group.append(InputMediaDocument(media=media, caption=caption))
    await bot.send_media_group(chat_id, group)
