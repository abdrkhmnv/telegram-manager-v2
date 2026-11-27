from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, str_enum
from database.models.chats import Chat
from database.models.enums import DeliveryStatus, ForwardMode, RuleStatus

forward_rule_sources = Table(
    "forward_rule_sources",
    Base.metadata,
    Column(
        "rule_id",
        BigInteger,
        ForeignKey("forward_rules.id", ondelete="CASCADE"),
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

forward_rule_destinations = Table(
    "forward_rule_destinations",
    Base.metadata,
    Column(
        "rule_id",
        BigInteger,
        ForeignKey("forward_rules.id", ondelete="CASCADE"),
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


class ForwardRule(TimestampMixin, Base):
    """Manba chatlardan manzil chatlarga yo'naltirish qoidasi."""

    __tablename__ = "forward_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    mode: Mapped[ForwardMode] = mapped_column(str_enum(ForwardMode, "forward_mode"))
    status: Mapped[RuleStatus] = mapped_column(
        str_enum(RuleStatus, "rule_status"),
        default=RuleStatus.ACTIVE,
        server_default=RuleStatus.ACTIVE.value,
        index=True,
    )
    include_keywords: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    exclude_keywords: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # Bo'sh ro'yxat = barcha media turlari ruxsat etilgan.
    media_types: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    duplicate_detection: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    # Faqat copy rejimida: yuborishdan oldin matn boshiga/oxiriga qo'shiladi.
    header_text: Mapped[str | None] = mapped_column(Text)
    footer_text: Mapped[str | None] = mapped_column(Text)

    sources: Mapped[list[Chat]] = relationship(secondary=forward_rule_sources, lazy="raise")
    destinations: Mapped[list[Chat]] = relationship(
        secondary=forward_rule_destinations, lazy="raise"
    )


class ForwardLog(TimestampMixin, Base):
    """Har bir (manba xabar -> manzil chat) yetkazib berish yozuvi.

    ``uq_forward_logs_delivery`` cheklovi idempotentlikni ta'minlaydi: bir xil
    xabar bir qoida bo'yicha bir manzilga ikki marta yuborilmaydi. Chat ID'lari
    Telegram ID sifatida saqlanadi — chat keshidan o'chirilsa ham tarix qoladi.
    """

    __tablename__ = "forward_logs"
    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "source_chat_telegram_id",
            "source_message_id",
            "destination_chat_telegram_id",
            name="uq_forward_logs_delivery",
        ),
        Index("ix_forward_logs_destination_hash", "destination_chat_telegram_id", "content_hash"),
        Index("ix_forward_logs_created_at", "created_at"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("forward_rules.id", ondelete="SET NULL")
    )
    mode: Mapped[ForwardMode] = mapped_column(str_enum(ForwardMode, "forward_mode"))
    source_chat_telegram_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    destination_chat_telegram_id: Mapped[int] = mapped_column(BigInteger)
    destination_message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[DeliveryStatus] = mapped_column(
        str_enum(DeliveryStatus, "delivery_status"),
        default=DeliveryStatus.PENDING,
        server_default=DeliveryStatus.PENDING.value,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(String(1000))
