from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Chat,
    DeliveryStatus,
    ForwardLog,
    ForwardMode,
    ForwardRule,
    RuleStatus,
)


class RuleExistsError(ValueError):
    """Shu nomli qoida allaqachon bor."""


class ForwardRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _with_chats(self) -> Any:
        return select(ForwardRule).options(
            selectinload(ForwardRule.sources), selectinload(ForwardRule.destinations)
        )

    async def list_all(self) -> list[ForwardRule]:
        rows = await self._session.scalars(self._with_chats().order_by(ForwardRule.id))
        return list(rows.all())

    async def active(self) -> list[ForwardRule]:
        rows = await self._session.scalars(
            self._with_chats().where(ForwardRule.status == RuleStatus.ACTIVE)
        )
        return list(rows.all())

    async def get(self, rule_id: int) -> ForwardRule | None:
        return await self._session.scalar(self._with_chats().where(ForwardRule.id == rule_id))

    async def create(
        self,
        *,
        name: str,
        mode: ForwardMode,
        source_ids: Sequence[int],
        destination_ids: Sequence[int],
    ) -> ForwardRule:
        if set(source_ids) & set(destination_ids):
            raise ValueError("Manba va manzil bir xil chat bo'lishi mumkin emas")
        if not source_ids or not destination_ids:
            raise ValueError("Kamida bitta manba va bitta manzil kerak")
        sources = list(await self._session.scalars(select(Chat).where(Chat.id.in_(source_ids))))
        destinations = list(
            await self._session.scalars(select(Chat).where(Chat.id.in_(destination_ids)))
        )
        rule = ForwardRule(name=" ".join(name.split())[:100], mode=mode)
        rule.sources = sources
        rule.destinations = destinations
        try:
            async with self._session.begin_nested():
                self._session.add(rule)
        except IntegrityError as exc:
            raise RuleExistsError(rule.name) from exc
        return rule

    async def update_fields(self, rule_id: int, **values: Any) -> bool:
        result = await self._session.execute(
            update(ForwardRule).where(ForwardRule.id == rule_id).values(**values)
        )
        return bool(getattr(result, "rowcount", 0))

    async def delete(self, rule_id: int) -> bool:
        result = await self._session.execute(delete(ForwardRule).where(ForwardRule.id == rule_id))
        return bool(getattr(result, "rowcount", 0))

    async def recent_logs(self, rule_id: int, limit: int = 10) -> list[ForwardLog]:
        rows = await self._session.scalars(
            select(ForwardLog)
            .where(ForwardLog.rule_id == rule_id)
            .order_by(ForwardLog.created_at.desc(), ForwardLog.id.desc())
            .limit(limit)
        )
        return list(rows.all())

    async def counts_since(self, rule_id: int, since: datetime) -> dict[DeliveryStatus, int]:
        rows = await self._session.execute(
            select(ForwardLog.status, func.count())
            .where(ForwardLog.rule_id == rule_id, ForwardLog.created_at >= since)
            .group_by(ForwardLog.status)
        )
        return {status: int(count) for status, count in rows.all()}
