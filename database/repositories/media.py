from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import MediaFile, PostTemplateMedia


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, media_id: int) -> MediaFile | None:
        return await self._session.get(MediaFile, media_id)

    async def get_by_sha(self, sha256: str) -> MediaFile | None:
        return await self._session.scalar(select(MediaFile).where(MediaFile.sha256 == sha256))

    async def get_many(self, media_ids: list[int]) -> list[MediaFile]:
        """Berilgan tartibda qaytaradi (albom tartibi muhim)."""
        if not media_ids:
            return []
        rows = await self._session.scalars(select(MediaFile).where(MediaFile.id.in_(media_ids)))
        by_id = {m.id: m for m in rows.all()}
        return [by_id[i] for i in media_ids if i in by_id]

    async def add(self, media: MediaFile) -> MediaFile:
        self._session.add(media)
        await self._session.flush()
        return media

    async def page(self, limit: int, offset: int) -> tuple[list[MediaFile], int]:
        total = int(await self._session.scalar(select(func.count()).select_from(MediaFile)) or 0)
        rows = await self._session.scalars(
            select(MediaFile)
            .order_by(MediaFile.created_at.desc(), MediaFile.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.all()), total

    async def usage_count(self, media_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(PostTemplateMedia)
            .where(PostTemplateMedia.media_id == media_id)
        )
        return int(await self._session.scalar(statement) or 0)

    async def delete(self, media_id: int) -> bool:
        result = await self._session.execute(delete(MediaFile).where(MediaFile.id == media_id))
        return bool(getattr(result, "rowcount", 0))

    async def set_missing(self, media_id: int, missing: bool) -> None:
        media = await self._session.get(MediaFile, media_id)
        if media is not None:
            media.is_missing = missing
