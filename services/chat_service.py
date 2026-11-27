"""Dialoglarni sinxronlash va chat keshi bilan ishlash."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from database.connection import Database
from database.models import Chat, ChatCategory, ChatType
from database.repositories.categories import CategoryRepository
from database.repositories.chats import ChatRepository, ChatSnapshot
from utils.logger import get_logger
from utils.time_utils import utc_now

logger = get_logger(__name__)

CHANNEL_ID_OFFSET = 1_000_000_000_000

SECTION_TYPES: dict[str, tuple[ChatType, ...]] = {
    "chats": (ChatType.PRIVATE,),
    "groups": (ChatType.GROUP, ChatType.SUPERGROUP),
    "chans": (ChatType.CHANNEL,),
}


def snapshot_from_entity(entity: Any, name: str | None = None) -> ChatSnapshot | None:
    """Telethon entity'sini ``ChatSnapshot`` ga aylantiradi.

    ID'lar Telegram "marked" formatida: foydalanuvchi ``id``, oddiy guruh ``-id``,
    kanal/supergroup ``-100<id>`` (Telethon ``utils.get_peer_id`` bilan bir xil).
    Tark etilgan, o'chirilgan yoki taqiqlangan chatlar qaytarilmaydi.
    """
    kind = type(entity).__name__
    if getattr(entity, "left", False) or getattr(entity, "deactivated", False):
        return None
    username = getattr(entity, "username", None)
    if kind == "User":
        if getattr(entity, "deleted", False):
            return None
        full_name = " ".join(
            p
            for p in (getattr(entity, "first_name", None), getattr(entity, "last_name", None))
            if p
        )
        return ChatSnapshot(
            telegram_id=int(entity.id),
            chat_type=ChatType.PRIVATE,
            title=name or full_name or (username or str(entity.id)),
            username=username,
        )
    if kind == "Chat":
        return ChatSnapshot(
            telegram_id=-int(entity.id),
            chat_type=ChatType.GROUP,
            title=name or getattr(entity, "title", "") or str(entity.id),
            members_count=getattr(entity, "participants_count", None),
        )
    if kind == "Channel":
        chat_type = ChatType.SUPERGROUP if getattr(entity, "megagroup", False) else ChatType.CHANNEL
        return ChatSnapshot(
            telegram_id=-(CHANNEL_ID_OFFSET + int(entity.id)),
            chat_type=chat_type,
            title=name or getattr(entity, "title", "") or str(entity.id),
            username=username,
            members_count=getattr(entity, "participants_count", None),
        )
    return None


@dataclass(frozen=True, slots=True)
class SyncResult:
    total: int
    by_type: dict[ChatType, int] = field(default_factory=dict)
    marked_inaccessible: int = 0


@dataclass(frozen=True, slots=True)
class ChatPage:
    chats: list[Chat]
    total: int
    page: int
    pages: int


class ChatService:
    def __init__(
        self, database: Database, client_provider: Callable[[], Any], page_size: int = 8
    ) -> None:
        self._database = database
        self._client = client_provider
        self.page_size = page_size

    async def sync_dialogs(self) -> SyncResult:
        """Akkaunt ko'ra oladigan barcha dialoglarni bazaga yozadi."""
        client = self._client()
        snapshots: list[ChatSnapshot] = []
        async for dialog in client.iter_dialogs():
            snapshot = snapshot_from_entity(dialog.entity, getattr(dialog, "name", None))
            if snapshot is not None:
                snapshots.append(snapshot)
        async with self._database.session() as session:
            repo = ChatRepository(session)
            total = await repo.upsert_many(snapshots, utc_now())
            hidden = await repo.mark_inaccessible_except([s.telegram_id for s in snapshots])
        counts = Counter(s.chat_type for s in {s.telegram_id: s for s in snapshots}.values())
        logger.info("Dialoglar sinxronlandi", extra={"total": total, "hidden": hidden})
        return SyncResult(total=total, by_type=dict(counts), marked_inaccessible=hidden)

    async def page(
        self,
        chat_types: Sequence[ChatType] | None,
        page: int,
        *,
        query: str | None = None,
        accessible_only: bool = True,
    ) -> ChatPage:
        async with self._database.session() as session:
            repo = ChatRepository(session)
            total = await repo.count(query, chat_types=chat_types, accessible_only=accessible_only)
            pages = max(1, -(-total // self.page_size))
            page = min(max(0, page), pages - 1)
            chats = await repo.search(
                query,
                chat_types=chat_types,
                accessible_only=accessible_only,
                limit=self.page_size,
                offset=page * self.page_size,
            )
        return ChatPage(chats=chats, total=total, page=page, pages=pages)

    async def get(self, chat_id: int) -> Chat | None:
        async with self._database.session() as session:
            return await ChatRepository(session).get(chat_id)

    async def get_many(self, chat_ids: Sequence[int]) -> list[Chat]:
        async with self._database.session() as session:
            return await ChatRepository(session).get_many(chat_ids)

    async def toggle_saved(self, chat_id: int) -> bool | None:
        async with self._database.session() as session:
            repo = ChatRepository(session)
            chat = await repo.get(chat_id)
            if chat is None:
                return None
            await repo.set_saved(chat_id, not chat.is_saved)
            return chat.is_saved

    async def categories(self) -> list[ChatCategory]:
        async with self._database.session() as session:
            return await CategoryRepository(session).list_all()

    async def category(self, category_id: int) -> tuple[ChatCategory | None, list[Chat]]:
        async with self._database.session() as session:
            repo = CategoryRepository(session)
            category = await repo.get(category_id)
            chats = await repo.chats_in_category(category_id) if category else []
            return category, chats

    async def chat_category_ids(self, chat_id: int) -> set[int]:
        async with self._database.session() as session:
            return await CategoryRepository(session).category_ids_for_chat(chat_id)

    async def toggle_category(self, chat_id: int, category_id: int) -> bool:
        async with self._database.session() as session:
            return await CategoryRepository(session).toggle(chat_id, category_id)

    async def create_category(self, name: str, chat_id: int | None = None) -> ChatCategory:
        async with self._database.session() as session:
            repo = CategoryRepository(session)
            category = await repo.create(name)
            if chat_id is not None:
                await session.flush()
                await repo.toggle(chat_id, category.id)
            return category

    async def delete_category(self, category_id: int) -> bool:
        async with self._database.session() as session:
            return await CategoryRepository(session).delete(category_id)
