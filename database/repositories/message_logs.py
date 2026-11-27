from __future__ import annotations

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from database.models import DeliveryStatus, MessageLog, MessageOperation, OperationSource
from utils.helpers import truncate

_ERROR_LIMIT = 1000
_PREVIEW_LIMIT = 100


class MessageLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        operation: MessageOperation,
        source: OperationSource,
        chat_telegram_id: int,
        status: DeliveryStatus,
        message_id: int | None = None,
        error: str | None = None,
        preview: str | None = None,
    ) -> MessageLog:
        entry = MessageLog(
            operation=operation,
            source=source,
            chat_telegram_id=chat_telegram_id,
            message_id=message_id,
            status=status,
            error=truncate(error, _ERROR_LIMIT) if error else None,
            preview=truncate(" ".join(preview.split()), _PREVIEW_LIMIT) if preview else None,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get(self, log_id: int) -> MessageLog | None:
        return await self._session.get(MessageLog, log_id)

    def _sent_not_deleted(self) -> ColumnElement[bool]:
        deleted = aliased(MessageLog)
        return and_(
            MessageLog.operation == MessageOperation.SEND,
            MessageLog.source == OperationSource.MANUAL,
            MessageLog.status == DeliveryStatus.SUCCESS,
            MessageLog.message_id.is_not(None),
            ~exists().where(
                deleted.operation == MessageOperation.DELETE,
                deleted.status == DeliveryStatus.SUCCESS,
                deleted.chat_telegram_id == MessageLog.chat_telegram_id,
                deleted.message_id == MessageLog.message_id,
            ),
        )

    async def sent_page(self, limit: int, offset: int) -> tuple[list[MessageLog], int]:
        condition = self._sent_not_deleted()
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(MessageLog).where(condition)
            )
            or 0
        )
        rows = await self._session.scalars(
            select(MessageLog)
            .where(condition)
            .order_by(MessageLog.created_at.desc(), MessageLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.all()), total
