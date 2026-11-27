"""Forwarder: qoidalarni boshqarish (CRUD) va real vaqtda yo'naltirish.

Ikki rejim:
* ``native`` — Telegram'ning oddiy forward'i (manba ko'rsatiladi, Telegram ruxsat bergan joyda).
* ``copy`` — yangi xabar sifatida yuboriladi (forward sarlavhasisiz), formatlash va media saqlanadi.

Himoyalangan kontent (``noforwards``) har ikki rejimda ham o'tkazib yuboriladi — tizim
Telegram'ning kontent himoyasini chetlab o'tmaydi.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from telethon import events
from telethon.errors import FloodWaitError, RPCError

from core.telegram_errors import describe_error, with_flood_wait
from database.connection import Database
from database.models import DeliveryStatus, ForwardLog, ForwardMode, ForwardRule, RuleStatus
from database.repositories.forwarding import ForwardLogRepository
from database.repositories.rules import ForwardRuleRepository
from utils.helpers import sha256_text
from utils.logger import get_logger
from utils.time_utils import utc_now

logger = get_logger(__name__)

MEDIA_KINDS = ("text", "photo", "video", "animation", "document", "audio", "voice", "other")
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError, OSError)
RELOAD_INTERVAL = 60.0
MAX_IN_FLIGHT = 200
RECENT_SENT_LIMIT = 5000


# ------------------------------------------------------------------ helpers
def media_kind(message: Any) -> str:
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "gif", None):
        return "animation"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "document", None):
        return "document"
    media = getattr(message, "media", None)
    if media is None or type(media).__name__ == "MessageMediaWebPage":
        return "text"
    return "other"


def message_text(messages: Sequence[Any]) -> str:
    for message in messages:
        text = getattr(message, "raw_text", None) or getattr(message, "message", None)
        if text:
            return str(text)
    return ""


def content_hash(messages: Sequence[Any]) -> str:
    parts = [message_text(messages)]
    for message in messages:
        for attr in ("photo", "document"):
            media = getattr(message, attr, None)
            if media is not None and getattr(media, "id", None) is not None:
                parts.append(f"{attr}:{media.id}")
    return sha256_text("\n".join(parts))


@dataclass(frozen=True, slots=True)
class RuleSnapshot:
    id: int
    name: str
    mode: ForwardMode
    sources: frozenset[int]
    destinations: tuple[int, ...]
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    media_types: frozenset[str] = frozenset()
    dedupe: bool = False
    header: str | None = None
    footer: str | None = None

    @classmethod
    def from_rule(cls, rule: ForwardRule) -> RuleSnapshot:
        return cls(
            id=rule.id,
            name=rule.name,
            mode=rule.mode,
            sources=frozenset(c.telegram_id for c in rule.sources if c.is_accessible),
            destinations=tuple(c.telegram_id for c in rule.destinations if c.is_accessible),
            include=tuple(k.casefold() for k in rule.include_keywords or ()),
            exclude=tuple(k.casefold() for k in rule.exclude_keywords or ()),
            media_types=frozenset(rule.media_types or ()),
            dedupe=rule.duplicate_detection,
            header=rule.header_text,
            footer=rule.footer_text,
        )


def rule_matches(rule: RuleSnapshot, text: str, kinds: Iterable[str]) -> bool:
    folded = text.casefold()
    if rule.include and not any(k in folded for k in rule.include):
        return False
    if any(k in folded for k in rule.exclude):
        return False
    return not rule.media_types or bool(set(kinds) & rule.media_types)


def compose(header: str | None, body: str | None, footer: str | None) -> str:
    return "\n\n".join(part for part in (header, body, footer) if part and part.strip())


# --------------------------------------------------------------- CRUD service
class ForwardRuleService:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._listeners: list[Callable[[], Awaitable[None]]] = []

    def on_change(self, listener: Callable[[], Awaitable[None]]) -> None:
        self._listeners.append(listener)

    async def _changed(self) -> None:
        for listener in self._listeners:
            try:
                await listener()
            except Exception:
                logger.exception("Qoidalarni qayta yuklashda xato")

    async def list_all(self) -> list[ForwardRule]:
        async with self._database.session() as session:
            return await ForwardRuleRepository(session).list_all()

    async def get(self, rule_id: int) -> ForwardRule | None:
        async with self._database.session() as session:
            return await ForwardRuleRepository(session).get(rule_id)

    async def create(
        self,
        name: str,
        mode: ForwardMode,
        source_ids: Sequence[int],
        destination_ids: Sequence[int],
    ) -> ForwardRule:
        async with self._database.session() as session:
            rule = await ForwardRuleRepository(session).create(
                name=name, mode=mode, source_ids=source_ids, destination_ids=destination_ids
            )
        await self._changed()
        return rule

    async def update(self, rule_id: int, **values: Any) -> bool:
        async with self._database.session() as session:
            changed = await ForwardRuleRepository(session).update_fields(rule_id, **values)
        await self._changed()
        return changed

    async def set_status(self, rule_id: int, status: RuleStatus) -> bool:
        return await self.update(rule_id, status=status)

    async def delete(self, rule_id: int) -> bool:
        async with self._database.session() as session:
            deleted = await ForwardRuleRepository(session).delete(rule_id)
        await self._changed()
        return deleted

    async def recent_logs(self, rule_id: int) -> list[ForwardLog]:
        async with self._database.session() as session:
            return await ForwardRuleRepository(session).recent_logs(rule_id)

    async def counts_last_day(self, rule_id: int) -> dict[DeliveryStatus, int]:
        async with self._database.session() as session:
            return await ForwardRuleRepository(session).counts_since(
                rule_id, utc_now() - timedelta(days=1)
            )


# ------------------------------------------------------------ runtime component
class ForwarderComponent:
    """Telethon hodisalarini tinglaydi va faol qoidalar bo'yicha yetkazib beradi."""

    name = "forwarder"

    def __init__(
        self,
        database: Database,
        client_provider: Callable[[], Any],
        *,
        retries: int = 3,
        dedupe_window: timedelta = timedelta(hours=24),
        delay_seconds: float = 1.0,
        concurrency: int = 4,
        reload_interval: float = RELOAD_INTERVAL,
        retry_base: float = 2.0,
    ) -> None:
        self._database = database
        self._client = client_provider
        self._retries = max(1, retries)
        self._dedupe_window = dedupe_window
        self._delay = delay_seconds
        self._semaphore = asyncio.Semaphore(concurrency)
        self._reload_interval = reload_interval
        self._retry_base = retry_base
        self._by_source: dict[int, list[RuleSnapshot]] = {}
        self._tasks: set[asyncio.Task[int]] = set()
        self._reloader: asyncio.Task[None] | None = None
        self._recent_sent: OrderedDict[tuple[int, int], None] = OrderedDict()
        self._handlers: list[tuple[Any, Any]] = []

    @property
    def is_running(self) -> bool:
        return self._reloader is not None and not self._reloader.done()

    @property
    def rule_count(self) -> int:
        return len({r.id for rules in self._by_source.values() for r in rules})

    async def reload(self) -> None:
        async with self._database.session() as session:
            rules = await ForwardRuleRepository(session).active()
        by_source: dict[int, list[RuleSnapshot]] = {}
        for rule in rules:
            snapshot = RuleSnapshot.from_rule(rule)
            for source in snapshot.sources:
                by_source.setdefault(source, []).append(snapshot)
        self._by_source = by_source

    async def start(self) -> None:
        await self.reload()
        client = self._client()
        for callback, event in (
            (self._on_message, events.NewMessage()),
            (self._on_album, events.Album()),
        ):
            client.add_event_handler(callback, event)
            self._handlers.append((callback, event))
        self._reloader = asyncio.create_task(self._reload_loop(), name="forwarder-reload")

    async def stop(self) -> None:
        client = self._client()
        for callback, event in self._handlers:
            client.remove_event_handler(callback, event)
        self._handlers.clear()
        if self._reloader is not None:
            self._reloader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reloader
            self._reloader = None
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=20)

    async def _reload_loop(self) -> None:
        while True:
            await asyncio.sleep(self._reload_interval)
            try:
                await self.reload()
            except Exception:
                logger.exception("Forward qoidalarini yangilashda xato")

    def _spawn(self, chat_id: int, messages: list[Any]) -> None:
        if chat_id not in self._by_source:
            return
        if len(self._tasks) >= MAX_IN_FLIGHT:
            logger.warning("Forward navbati to'lgan, xabar o'tkazib yuborildi")
            return
        task = asyncio.create_task(self.process(chat_id, messages))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _on_message(self, event: Any) -> None:
        message = event.message
        if getattr(message, "grouped_id", None):
            return  # albom events.Album orqali bir butun keladi
        self._spawn(event.chat_id, [message])

    async def _on_album(self, event: Any) -> None:
        self._spawn(event.chat_id, list(event.messages))

    def _remember_sent(self, chat_id: int, result: Any) -> None:
        items = result if isinstance(result, list) else [result]
        for item in items:
            message_id = getattr(item, "id", None)
            if message_id is not None:
                self._recent_sent[(chat_id, int(message_id))] = None
        while len(self._recent_sent) > RECENT_SENT_LIMIT:
            self._recent_sent.popitem(last=False)

    async def process(self, chat_id: int, messages: list[Any]) -> int:
        """Xabar(lar)ni mos qoidalar bo'yicha yetkazadi. Qaytaradi: muvaffaqiyatli yetkazishlar."""
        if not messages:
            return 0
        first = messages[0]
        # Forwarder'ning o'zi yuborgan xabarlar qayta yo'naltirilmaydi (zanjir/halqa himoyasi).
        if (chat_id, int(first.id)) in self._recent_sent:
            return 0
        rules = self._by_source.get(chat_id, [])
        text = message_text(messages)
        kinds = {media_kind(m) for m in messages}
        digest = content_hash(messages)
        delivered = 0
        for rule in rules:
            if not rule_matches(rule, text, kinds):
                continue
            for destination in rule.destinations:
                async with self._semaphore:
                    if await self.deliver(rule, chat_id, messages, destination, digest):
                        delivered += 1
                    await asyncio.sleep(self._delay)
        return delivered

    async def deliver(
        self, rule: RuleSnapshot, source: int, messages: list[Any], destination: int, digest: str
    ) -> bool:
        first = messages[0]
        async with self._database.session() as session:
            log_id = await ForwardLogRepository(session).reserve(
                rule_id=rule.id,
                mode=rule.mode,
                source_chat_telegram_id=source,
                source_message_id=int(first.id),
                destination_chat_telegram_id=destination,
                content_hash=digest,
            )
        if log_id is None:
            return False  # allaqachon qayta ishlangan (idempotentlik)

        skip_reason = await self._skip_reason(rule, messages, destination, digest)
        if skip_reason:
            async with self._database.session() as session:
                await ForwardLogRepository(session).mark_skipped(log_id, skip_reason)
            return False

        last_error = "noma'lum xato"
        for attempt in range(1, self._retries + 1):
            try:
                result = await self._send(rule, source, messages, destination)
            except FloodWaitError as exc:
                last_error = describe_error(exc)
                break
            except TRANSIENT_ERRORS as exc:
                last_error = describe_error(exc)
                await asyncio.sleep(min(self._retry_base**attempt, 30))
                continue
            except (RPCError, ValueError) as exc:
                last_error = describe_error(exc)
                break
            self._remember_sent(destination, result)
            first_result = result[0] if isinstance(result, list) and result else result
            async with self._database.session() as session:
                await ForwardLogRepository(session).mark_success(
                    log_id, getattr(first_result, "id", None)
                )
            return True
        logger.warning(
            "Forward yetkazilmadi",
            extra={"rule": rule.id, "destination": destination, "error": last_error},
        )
        async with self._database.session() as session:
            await ForwardLogRepository(session).mark_failed(log_id, last_error)
        return False

    async def _skip_reason(
        self, rule: RuleSnapshot, messages: list[Any], destination: int, digest: str
    ) -> str | None:
        if any(getattr(m, "noforwards", False) for m in messages):
            return "himoyalangan kontent (forward/nusxalash taqiqlangan)"
        if rule.dedupe:
            since: datetime = utc_now() - self._dedupe_window
            async with self._database.session() as session:
                if await ForwardLogRepository(session).has_recent_duplicate(
                    destination, digest, since
                ):
                    return "takroriy kontent"
        return None

    async def _send(
        self, rule: RuleSnapshot, source: int, messages: list[Any], destination: int
    ) -> Any:
        client = self._client()
        if rule.mode is ForwardMode.NATIVE:
            return await with_flood_wait(
                lambda: client.forward_messages(
                    destination, [m.id for m in messages], from_peer=source
                ),
                operation="forward",
            )
        if len(messages) == 1:
            message = messages[0]
            if not rule.header and not rule.footer:
                return await with_flood_wait(
                    lambda: client.send_message(destination, message), operation="copy"
                )
            has_media = media_kind(message) not in ("text",)
            return await with_flood_wait(
                lambda: client.send_message(
                    destination,
                    compose(rule.header, message.text, rule.footer),
                    file=message.media if has_media else None,
                    parse_mode="html",
                    link_preview=False,
                ),
                operation="copy",
            )
        captions = [m.text or "" for m in messages]
        captions[0] = compose(rule.header, captions[0], rule.footer)
        return await with_flood_wait(
            lambda: client.send_file(
                destination, [m.media for m in messages], caption=captions, parse_mode="html"
            ),
            operation="copy_album",
        )
