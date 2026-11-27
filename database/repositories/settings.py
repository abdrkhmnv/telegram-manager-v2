from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Setting

_MAX_KEY_LENGTH = 100


def _check_key(key: str) -> str:
    if not key or len(key) > _MAX_KEY_LENGTH:
        raise ValueError(f"Sozlama kaliti 1..{_MAX_KEY_LENGTH} belgidan iborat bo'lishi kerak")
    return key


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str, default: Any = None) -> Any:
        value = await self._session.scalar(select(Setting.value).where(Setting.key == key))
        return default if value is None else value

    async def set(self, key: str, value: Any) -> None:
        """Qiymatni yozadi yoki yangilaydi (atomik UPSERT)."""
        if value is None:
            raise ValueError("Sozlama qiymati None bo'lishi mumkin emas; o'chirish uchun delete()")
        statement = pg_insert(Setting).values(key=_check_key(key), value=value)
        statement = statement.on_conflict_do_update(
            index_elements=[Setting.key],
            set_={"value": statement.excluded["value"], "updated_at": func.now()},
        )
        await self._session.execute(statement)

    async def delete(self, key: str) -> bool:
        result = await self._session.execute(delete(Setting).where(Setting.key == key))
        return bool(getattr(result, "rowcount", 0))
