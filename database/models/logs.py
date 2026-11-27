from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin, str_enum
from database.models.enums import DeliveryStatus, MessageOperation, OperationSource, RunStatus


class MessageLog(TimestampMixin, Base):
    """Yuborish/tahrirlash/o'chirish operatsiyalari tarixi (statistika manbai)."""

    __tablename__ = "message_logs"
    __table_args__ = (Index("ix_message_logs_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    operation: Mapped[MessageOperation] = mapped_column(
        str_enum(MessageOperation, "message_operation")
    )
    source: Mapped[OperationSource] = mapped_column(str_enum(OperationSource, "operation_source"))
    chat_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[DeliveryStatus] = mapped_column(str_enum(DeliveryStatus, "delivery_status"))
    error: Mapped[str | None] = mapped_column(String(1000))
    preview: Mapped[str | None] = mapped_column(String(100))


class TaskLog(Base):
    """Fon vazifalari bajarilish tarixi."""

    __tablename__ = "task_logs"
    __table_args__ = (Index("ix_task_logs_started_at", "started_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("autopost_tasks.id", ondelete="SET NULL"), index=True
    )
    task_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus, "run_status"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(1000))
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class ActivityLog(Base):
    """Boshqaruv panelidagi muhim harakatlar auditi. Maxfiy qiymatlar yozilmaydi."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
