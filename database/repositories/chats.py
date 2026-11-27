from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Chat, ChatType
from utils.helpers import escape_like
from utils.time_utils import ensure_utc

_UPSERT_BATCH = 500
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class ChatSnapshot:
    """Telegram'dan olingan dialog haqidagi minimal ma'lumot."""

    telegram_id: int
    chat_type: ChatType
    title: str
    username: str | None = None
    members_count: int | None = None


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, snapshots: Sequence[ChatSnapshot], synced_at: datetime) -> int:
        """Dialoglarni bir nechta INSERT ... ON CONFLICT so'rovi bilan sinxronlaydi.

        Bir partiyada takrorlangan ``telegram_id`` bo'lsa, oxirgisi olinadi
        (PostgreSQL bir so'rovda bitta qatorni ikki marta yangilay olmaydi).
        Foydalanuvchi belgilari (``is_saved``, toifalar) o'zgartirilmaydi.
        """
        synced = ensure_utc(synced_at)
        unique = {snapshot.telegram_id: snapshot for snapshot in snapshots}
        rows = [
            {
                "telegram_id": s.telegram_id,
                "chat_type": s.chat_type,
                "title": s.title[:255],
                "username": s.username,
                "members_count": s.members_count,
                "is_accessible": True,
                "last_synced_at": synced,
            }
            for s in unique.values()
        ]
        for start in range(0, len(rows), _UPSERT_BATCH):
            statement = pg_insert(Chat).values(rows[start : start + _UPSERT_BATCH])
            excluded = statement.excluded
            statement = statement.on_conflict_do_update(
                index_elements=[Chat.telegram_id],
                set_={
                    "chat_type": excluded.chat_type,
                    "title": excluded.title,
                    "username": excluded.username,
                    "members_count": excluded.members_count,
                    "is_accessible": excluded.is_accessible,
                    "last_synced_at": excluded.last_synced_at,
                    "updated_at": func.now(),
                },
            )
            await self._session.execute(statement)
        return len(rows)

    async def get_by_telegram_id(self, telegram_id: int) -> Chat | None:
        return await self._session.scalar(select(Chat).where(Chat.telegram_id == telegram_id))

    async def set_saved(self, chat_id: int, saved: bool) -> bool:
        chat = await self._session.get(Chat, chat_id)
        if chat is None:
            return False
        chat.is_saved = saved
        await self._session.flush()
        return True

    @staticmethod
    def _filters(
        query: str | None, chat_type: ChatType | None, saved_only: bool
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if query and query.strip():
            pattern = f"%{escape_like(query.strip().removeprefix('@'))}%"
            conditions.append(
                or_(
                    Chat.title.ilike(pattern, escape="\\"),
                    Chat.username.ilike(pattern, escape="\\"),
                )
            )
        if chat_type is not None:
            conditions.append(Chat.chat_type == chat_type)
        if saved_only:
            conditions.append(Chat.is_saved.is_(True))
        return conditions

    async def search(
        self,
        query: str | None = None,
        *,
        chat_type: ChatType | None = None,
        saved_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Chat]:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)
        statement = (
            select(Chat)
            .where(*self._filters(query, chat_type, saved_only))
            .order_by(func.lower(Chat.title), Chat.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())

    async def count(
        self,
        query: str | None = None,
        *,
        chat_type: ChatType | None = None,
        saved_only: bool = False,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(Chat)
            .where(*self._filters(query, chat_type, saved_only))
        )
        return int(await self._session.scalar(statement) or 0)
