from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, str_enum
from database.models.chats import Chat
from database.models.enums import AutopostKind, PostStatus, Recurrence, TaskStatus

autopost_task_destinations = Table(
    "autopost_task_destinations",
    Base.metadata,
    Column(
        "task_id",
        BigInteger,
        ForeignKey("autopost_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "chat_id",
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class AutopostTask(TimestampMixin, Base):
    """Rejalashtirilgan yoki tasodifiy intervalli autopost vazifasi.

    Bajarish uchun "ijara" (lease) mexanizmi: ishchi vazifani ``locked_by`` /
    ``locked_until`` orqali atomik egallaydi (``FOR UPDATE SKIP LOCKED``).
    Jarayon qulasa, ijara muddati tugagach vazifa avtomatik qayta egallanadi.
    Vaqtlar UTC; ``time_of_day`` va faol soatlar — mahalliy (Asia/Tashkent) vaqt.
    """

    __tablename__ = "autopost_tasks"
    __table_args__ = (
        Index("ix_autopost_tasks_due", "status", "next_run_at"),
        CheckConstraint(
            "weekdays_mask IS NULL OR weekdays_mask BETWEEN 1 AND 127", name="weekdays_mask_range"
        ),
        CheckConstraint(
            "min_interval_seconds IS NULL OR max_interval_seconds IS NULL"
            " OR min_interval_seconds <= max_interval_seconds",
            name="interval_order",
        ),
        CheckConstraint(
            "kind <> 'random' OR (min_interval_seconds IS NOT NULL"
            " AND max_interval_seconds IS NOT NULL)",
            name="random_requires_interval",
        ),
        CheckConstraint(
            "kind <> 'scheduled' OR recurrence IS NOT NULL", name="scheduled_requires_recurrence"
        ),
        CheckConstraint("max_retries >= 0", name="max_retries_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[AutopostKind] = mapped_column(str_enum(AutopostKind, "autopost_kind"))
    status: Mapped[TaskStatus] = mapped_column(
        str_enum(TaskStatus, "task_status"),
        default=TaskStatus.ACTIVE,
        server_default=TaskStatus.ACTIVE.value,
    )
    recurrence: Mapped[Recurrence | None] = mapped_column(str_enum(Recurrence, "recurrence"))
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_of_day: Mapped[time | None] = mapped_column(Time)
    weekdays_mask: Mapped[int | None] = mapped_column(SmallInteger)
    min_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    max_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    active_from: Mapped[time | None] = mapped_column(Time)
    active_to: Mapped[time | None] = mapped_column(Time)
    template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("post_templates.id", ondelete="SET NULL"), index=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(64))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default=text("0")
    )
    max_retries: Mapped[int] = mapped_column(SmallInteger, default=3, server_default=text("3"))

    destinations: Mapped[list[Chat]] = relationship(
        secondary=autopost_task_destinations, lazy="raise"
    )


class AutopostQueueItem(TimestampMixin, Base):
    """Tasodifiy autopost uchun kontent navbati elementi."""

    __tablename__ = "autopost_queue_items"
    __table_args__ = (
        UniqueConstraint("task_id", "template_id", name="uq_autopost_queue_items_task_template"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("autopost_tasks.id", ondelete="CASCADE")
    )
    template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("post_templates.id", ondelete="CASCADE"), index=True
    )
    times_posted: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScheduledPost(TimestampMixin, Base):
    """Vazifaning aniq bir bajarilishi (bitta manzil, bitta vaqt).

    ``uq_scheduled_posts_occurrence`` — bir vazifa bir vaqtda bir manzilga
    faqat bir marta yozuv yaratishi mumkin (takroriy bajarilishdan himoya).
    """

    __tablename__ = "scheduled_posts"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "destination_chat_telegram_id",
            "scheduled_for",
            name="uq_scheduled_posts_occurrence",
        ),
        Index("ix_scheduled_posts_status_scheduled_for", "status", "scheduled_for"),
        Index("ix_scheduled_posts_created_at", "created_at"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("autopost_tasks.id", ondelete="SET NULL")
    )
    template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("post_templates.id", ondelete="SET NULL")
    )
    kind: Mapped[AutopostKind] = mapped_column(str_enum(AutopostKind, "autopost_kind"))
    destination_chat_telegram_id: Mapped[int] = mapped_column(BigInteger)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[PostStatus] = mapped_column(
        str_enum(PostStatus, "post_status"),
        default=PostStatus.PENDING,
        server_default=PostStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    sent_message_id: Mapped[int | None] = mapped_column(BigInteger)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(1000))
