from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import PostTemplate, PostTemplateMedia


def _auto_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class TemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, template_id: int) -> PostTemplate | None:
        return await self._session.scalar(
            select(PostTemplate)
            .options(selectinload(PostTemplate.media_items).selectinload(PostTemplateMedia.media))
            .where(PostTemplate.id == template_id)
        )

    async def create(
        self, *, text: str | None, media_ids: Sequence[int], name: str | None = None
    ) -> PostTemplate:
        if not (text and text.strip()) and not media_ids:
            raise ValueError("Bo'sh post saqlanmaydi")
        if len(media_ids) > 10:
            raise ValueError("Postda ko'pi bilan 10 ta media")
        template = PostTemplate(
            name=(name or _auto_name("post"))[:100], text=text, parse_mode="html"
        )
        template.media_items = [
            PostTemplateMedia(position=index, media_id=media_id)
            for index, media_id in enumerate(media_ids)
        ]
        self._session.add(template)
        await self._session.flush()
        return template

    async def replace_content(
        self, template_id: int, *, text: str | None, media_ids: Sequence[int]
    ) -> bool:
        template = await self._session.get(PostTemplate, template_id)
        if template is None:
            return False
        if not (text and text.strip()) and not media_ids:
            raise ValueError("Bo'sh post saqlanmaydi")
        template.text = text
        await self._session.execute(
            delete(PostTemplateMedia).where(PostTemplateMedia.template_id == template_id)
        )
        for index, media_id in enumerate(media_ids):
            self._session.add(
                PostTemplateMedia(template_id=template_id, position=index, media_id=media_id)
            )
        await self._session.flush()
        return True

    async def delete(self, template_id: int) -> None:
        await self._session.execute(delete(PostTemplate).where(PostTemplate.id == template_id))
