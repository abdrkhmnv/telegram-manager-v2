"""Userbot orqali xabar yuborish, tahrirlash va o'chirish (tarix bilan)."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from html import unescape
from typing import Any

from telethon.errors import RPCError

from core.telegram_errors import describe_error, with_flood_wait
from database.connection import Database
from database.models import (
    Chat,
    DeliveryStatus,
    MediaFile,
    MediaType,
    MessageLog,
    MessageOperation,
    OperationSource,
)
from database.repositories.chats import ChatRepository
from database.repositories.message_logs import MessageLogRepository
from services.media_service import MediaService
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_SEND_DELAY = 1.5
MAX_DESTINATIONS = 50
_TAG_RE = re.compile(r"<[^>]+>")

SEND_ERRORS: tuple[type[BaseException], ...] = (
    RPCError,
    ValueError,
    OSError,
    ConnectionError,
    TimeoutError,
)

Progress = Callable[[int, int], Awaitable[None]]


def plain_preview(html_text: str | None, media: Sequence[MediaFile] = ()) -> str:
    text = unescape(_TAG_RE.sub("", html_text or "")).strip()
    if media:
        kinds = ", ".join(sorted({m.media_type.value for m in media}))
        text = f"[{kinds}] {text}".strip()
    return text or "—"


@dataclass(frozen=True, slots=True)
class OutgoingContent:
    """Yuboriladigan kontent. ``text`` — HTML (Telegram formatlash teglari)."""

    text: str | None = None
    media: tuple[MediaFile, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.text and self.text.strip()) and not self.media


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    chat_id: int
    telegram_id: int
    title: str
    ok: bool
    message_id: int | None = None
    error: str | None = None


@dataclass(slots=True)
class SendReport:
    results: list[DeliveryResult] = field(default_factory=list)

    @property
    def sent(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> list[DeliveryResult]:
        return [r for r in self.results if not r.ok]


async def send_content(
    client: Any, media_service: MediaService, peer: int, content: OutgoingContent
) -> int:
    """Kontentni bitta chatga yuboradi va birinchi xabar ID'sini qaytaradi."""
    text = content.text or None
    if not content.media:
        message = await with_flood_wait(
            lambda: client.send_message(peer, text, parse_mode="html", link_preview=False),
            operation="send_message",
        )
        return int(message.id)
    paths = [await media_service.path_for(m) for m in content.media]
    if len(paths) == 1:
        media = content.media[0]
        message = await with_flood_wait(
            lambda: client.send_file(
                peer,
                paths[0],
                caption=text,
                parse_mode="html",
                voice_note=media.media_type is MediaType.VOICE,
                force_document=media.media_type is MediaType.DOCUMENT,
                supports_streaming=media.media_type is MediaType.VIDEO,
            ),
            operation="send_file",
        )
        return int(message.id)
    messages = await with_flood_wait(
        lambda: client.send_file(peer, paths, caption=text, parse_mode="html"),
        operation="send_album",
    )
    first = messages[0] if isinstance(messages, list) else messages
    return int(first.id)


class MessageService:
    def __init__(
        self,
        database: Database,
        client_provider: Callable[[], Any],
        media: MediaService,
        *,
        delay_seconds: float = DEFAULT_SEND_DELAY,
    ) -> None:
        self._database = database
        self._client = client_provider
        self._media = media
        self._delay = delay_seconds

    async def destinations(self, chat_ids: Sequence[int]) -> list[Chat]:
        async with self._database.session() as session:
            chats = await ChatRepository(session).get_many(chat_ids)
        return [c for c in chats if c.is_accessible]

    async def send(
        self,
        content: OutgoingContent,
        chat_ids: Sequence[int],
        *,
        progress: Progress | None = None,
        source: OperationSource = OperationSource.MANUAL,
    ) -> SendReport:
        """Ketma-ket yuboradi (parallel emas) — Telegram cheklovlariga rioya qilish uchun."""
        if content.is_empty:
            raise ValueError("Bo'sh xabarni yuborib bo'lmaydi")
        if len(chat_ids) > MAX_DESTINATIONS:
            raise ValueError(f"Bir yuborishda ko'pi bilan {MAX_DESTINATIONS} ta chat")
        chats = await self.destinations(chat_ids)
        report = SendReport()
        preview = plain_preview(content.text, content.media)
        client = self._client()
        for index, chat in enumerate(chats, start=1):
            try:
                message_id = await send_content(client, self._media, chat.telegram_id, content)
                result = DeliveryResult(chat.id, chat.telegram_id, chat.title, True, message_id)
            except SEND_ERRORS as exc:  # MediaMissingError ham OSError
                logger.warning(
                    "Xabar yuborilmadi",
                    extra={"chat": chat.telegram_id, "error": type(exc).__name__},
                )
                result = DeliveryResult(
                    chat.id, chat.telegram_id, chat.title, False, error=describe_error(exc)
                )
            report.results.append(result)
            await self._log(
                MessageOperation.SEND,
                source,
                chat.telegram_id,
                result.message_id,
                result.error,
                preview,
            )
            if progress is not None:
                await progress(index, len(chats))
            if index < len(chats):
                await asyncio.sleep(self._delay)
        return report

    async def _log(
        self,
        operation: MessageOperation,
        source: OperationSource,
        chat_telegram_id: int,
        message_id: int | None,
        error: str | None,
        preview: str | None,
    ) -> None:
        async with self._database.session() as session:
            await MessageLogRepository(session).add(
                operation=operation,
                source=source,
                chat_telegram_id=chat_telegram_id,
                message_id=message_id,
                status=DeliveryStatus.FAILED if error else DeliveryStatus.SUCCESS,
                error=error,
                preview=preview,
            )

    async def history(self, page: int, per_page: int = 8) -> tuple[list[MessageLog], int, int]:
        async with self._database.session() as session:
            repo = MessageLogRepository(session)
            _, total = await repo.sent_page(1, 0)
            pages = max(1, -(-total // per_page))
            page = min(max(0, page), pages - 1)
            items, _ = await repo.sent_page(per_page, page * per_page)
        return items, page, pages

    async def get_log(self, log_id: int) -> MessageLog | None:
        async with self._database.session() as session:
            return await MessageLogRepository(session).get(log_id)

    async def chat_title(self, telegram_id: int) -> str:
        async with self._database.session() as session:
            chat = await ChatRepository(session).get_by_telegram_id(telegram_id)
        return chat.title if chat else str(telegram_id)

    async def edit(self, log_id: int, html_text: str) -> str | None:
        """Tarixdagi xabarni tahrirlaydi. Qaytaradi: xato matni yoki ``None``."""
        log = await self.get_log(log_id)
        if log is None or log.message_id is None:
            return "Xabar topilmadi"
        message_id = log.message_id
        client = self._client()
        try:
            await with_flood_wait(
                lambda: client.edit_message(
                    log.chat_telegram_id,
                    message_id,
                    html_text,
                    parse_mode="html",
                    link_preview=False,
                ),
                operation="edit_message",
            )
            error = None
        except SEND_ERRORS as exc:
            error = describe_error(exc)
        await self._log(
            MessageOperation.EDIT,
            OperationSource.MANUAL,
            log.chat_telegram_id,
            message_id,
            error,
            plain_preview(html_text),
        )
        return error

    async def delete(self, log_id: int) -> str | None:
        """Xabarni hamma uchun o'chiradi. Qaytaradi: xato matni yoki ``None``."""
        log = await self.get_log(log_id)
        if log is None or log.message_id is None:
            return "Xabar topilmadi"
        message_id = log.message_id
        client = self._client()
        try:
            await with_flood_wait(
                lambda: client.delete_messages(log.chat_telegram_id, [message_id], revoke=True),
                operation="delete_messages",
            )
            error = None
        except SEND_ERRORS as exc:
            error = describe_error(exc)
        await self._log(
            MessageOperation.DELETE,
            OperationSource.MANUAL,
            log.chat_telegram_id,
            message_id,
            error,
            log.preview,
        )
        return error
