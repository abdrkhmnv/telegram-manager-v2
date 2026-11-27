from __future__ import annotations

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Chat, ChatCategory, chat_category_links

MAX_NAME_LENGTH = 64


class CategoryExistsError(ValueError):
    """Shu nomli toifa allaqachon mavjud."""


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[ChatCategory]:
        statement = select(ChatCategory).order_by(func.lower(ChatCategory.name))
        return list((await self._session.scalars(statement)).all())

    async def get(self, category_id: int) -> ChatCategory | None:
        return await self._session.get(ChatCategory, category_id)

    async def create(self, name: str) -> ChatCategory:
        clean = " ".join(name.split())
        if not clean or len(clean) > MAX_NAME_LENGTH:
            raise ValueError(f"Toifa nomi 1..{MAX_NAME_LENGTH} belgidan iborat bo'lishi kerak")
        category = ChatCategory(name=clean)
        try:
            async with self._session.begin_nested():
                self._session.add(category)
        except IntegrityError as exc:
            raise CategoryExistsError(clean) from exc
        return category

    async def delete(self, category_id: int) -> bool:
        result = await self._session.execute(
            delete(ChatCategory).where(ChatCategory.id == category_id)
        )
        return bool(getattr(result, "rowcount", 0))

    async def category_ids_for_chat(self, chat_id: int) -> set[int]:
        rows = await self._session.scalars(
            select(chat_category_links.c.category_id).where(
                chat_category_links.c.chat_id == chat_id
            )
        )
        return set(rows.all())

    async def toggle(self, chat_id: int, category_id: int) -> bool:
        """Chatni toifaga qo'shadi yoki olib tashlaydi. Qaytaradi: endi toifadami."""
        link = (chat_category_links.c.chat_id == chat_id) & (
            chat_category_links.c.category_id == category_id
        )
        removed = await self._session.execute(delete(chat_category_links).where(link))
        if getattr(removed, "rowcount", 0):
            return False
        await self._session.execute(
            insert(chat_category_links).values(chat_id=chat_id, category_id=category_id)
        )
        return True

    async def chats_in_category(self, category_id: int, limit: int = 50) -> list[Chat]:
        statement = (
            select(Chat)
            .join(chat_category_links, chat_category_links.c.chat_id == Chat.id)
            .where(chat_category_links.c.category_id == category_id)
            .order_by(func.lower(Chat.title))
            .limit(max(1, min(limit, 100)))
        )
        return list((await self._session.scalars(statement)).all())
