from __future__ import annotations

from datetime import datetime

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DeliveryStatus, ForwardLog, ForwardMode
from utils.helpers import truncate
from utils.time_utils import ensure_utc

_ERROR_LIMIT = 1000


class ForwardLogRepository:
    """Forward yetkazib berishlarini idempotent tarzda qayd etadi."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        rule_id: int,
        mode: ForwardMode,
        source_chat_telegram_id: int,
        source_message_id: int,
        destination_chat_telegram_id: int,
        content_hash: str | None = None,
    ) -> int | None:
        """Yetkazib berish uchun yozuv yaratadi.

        Qaytaradi: yangi yozuv ID'si; agar aynan shu yetkazib berish allaqachon
        mavjud bo'lsa — ``None`` (chaqiruvchi uni qayta yubormasligi kerak).
        """
        statement = (
            pg_insert(ForwardLog)
            .values(
                rule_id=rule_id,
                mode=mode,
                source_chat_telegram_id=source_chat_telegram_id,
                source_message_id=source_message_id,
                destination_chat_telegram_id=destination_chat_telegram_id,
                content_hash=content_hash,
                status=DeliveryStatus.PENDING,
                attempts=0,
            )
            .on_conflict_do_nothing(constraint="uq_forward_logs_delivery")
            .returning(ForwardLog.id)
        )
        return await self._session.scalar(statement)

    async def get(self, log_id: int) -> ForwardLog | None:
        return await self._session.get(ForwardLog, log_id)

    async def mark_success(self, log_id: int, destination_message_id: int | None) -> None:
        await self._session.execute(
            update(ForwardLog)
            .where(ForwardLog.id == log_id)
            .values(
                status=DeliveryStatus.SUCCESS,
                destination_message_id=destination_message_id,
                attempts=ForwardLog.attempts + 1,
                error=None,
            )
        )

    async def mark_failed(self, log_id: int, error: str) -> None:
        await self._session.execute(
            update(ForwardLog)
            .where(ForwardLog.id == log_id)
            .values(
                status=DeliveryStatus.FAILED,
                attempts=ForwardLog.attempts + 1,
                error=truncate(error, _ERROR_LIMIT),
            )
        )

    async def mark_skipped(self, log_id: int, reason: str) -> None:
        await self._session.execute(
            update(ForwardLog)
            .where(ForwardLog.id == log_id)
            .values(status=DeliveryStatus.SKIPPED, error=truncate(reason, _ERROR_LIMIT))
        )

    async def has_recent_duplicate(
        self, destination_chat_telegram_id: int, content_hash: str, since: datetime
    ) -> bool:
        """Shu manzilga shu kontent ``since`` dan beri muvaffaqiyatli yuborilganmi."""
        statement = select(
            exists().where(
                ForwardLog.destination_chat_telegram_id == destination_chat_telegram_id,
                ForwardLog.content_hash == content_hash,
                ForwardLog.status == DeliveryStatus.SUCCESS,
                ForwardLog.created_at >= ensure_utc(since),
            )
        )
        return bool(await self._session.scalar(statement))
