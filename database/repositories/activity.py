from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ActivityLog

_MAX_ACTION_LENGTH = 100


class ActivityLogRepository:
    """Boshqaruv panelidagi harakatlar auditi.

    ``details`` ga maxfiy qiymatlar (token, parol, kod) yozilmasligi kerak —
    bu chaqiruvchining mas'uliyati; repozitoriy faqat JSON-serializatsiya qilinadigan
    oddiy qiymatlarni qabul qiladi.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, action: str, *, actor_telegram_id: int | None, details: dict[str, Any] | None = None
    ) -> ActivityLog:
        if not action or len(action) > _MAX_ACTION_LENGTH:
            raise ValueError("action 1..100 belgidan iborat bo'lishi kerak")
        entry = ActivityLog(
            action=action, actor_telegram_id=actor_telegram_id, details=dict(details or {})
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def recent(self, limit: int = 20) -> list[ActivityLog]:
        limit = max(1, min(limit, 100))
        statement = (
            select(ActivityLog)
            .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())
