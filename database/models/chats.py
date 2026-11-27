from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, str_enum
from database.models.enums import ChatType

chat_category_links = Table(
    "chat_category_links",
    Base.metadata,
    Column("chat_id", BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "category_id",
        BigInteger,
        ForeignKey("chat_categories.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class ChatCategory(TimestampMixin, Base):
    """Foydalanuvchi yaratgan chat toifalari (masalan: "Ish", "Yangiliklar")."""

    __tablename__ = "chat_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    chats: Mapped[list[Chat]] = relationship(
        secondary=chat_category_links, back_populates="categories", lazy="raise"
    )


class Chat(TimestampMixin, Base):
    """Akkaunt kira oladigan dialoglar keshi (Telegram'dan sinxronlanadi)."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    chat_type: Mapped[ChatType] = mapped_column(str_enum(ChatType, "chat_type"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_accessible: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    members_count: Mapped[int | None] = mapped_column(Integer)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    categories: Mapped[list[ChatCategory]] = relationship(
        secondary=chat_category_links, back_populates="chats", lazy="raise"
    )
