from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, str_enum
from database.models.enums import MediaType


class MediaFile(TimestampMixin, Base):
    """Saqlash katalogidagi media fayl metama'lumotlari.

    ``storage_path`` — ``STORAGE_DIR`` ga nisbatan yo'l (mutlaq yo'l saqlanmaydi).
    ``sha256`` noyobligi bir xil faylni qayta yuklab olishning oldini oladi.
    """

    __tablename__ = "media_files"
    __table_args__ = (CheckConstraint("size_bytes >= 0", name="size_non_negative"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    storage_path: Mapped[str] = mapped_column(String(512), unique=True)
    original_name: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(127))
    media_type: Mapped[MediaType] = mapped_column(str_enum(MediaType, "media_type"))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    is_missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class PostTemplate(TimestampMixin, Base):
    """Qayta ishlatiladigan post: matn va (ixtiyoriy) albom ko'rinishidagi media."""

    __tablename__ = "post_templates"
    __table_args__ = (
        CheckConstraint(
            "parse_mode IS NULL OR parse_mode IN ('html', 'markdown')", name="parse_mode_valid"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    text: Mapped[str | None] = mapped_column(Text)
    parse_mode: Mapped[str | None] = mapped_column(String(16))

    media_items: Mapped[list[PostTemplateMedia]] = relationship(
        back_populates="template",
        order_by="PostTemplateMedia.position",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class PostTemplateMedia(Base):
    """Post shabloniga biriktirilgan media (tartib bilan; albom 10 tagacha)."""

    __tablename__ = "post_template_media"
    __table_args__ = (CheckConstraint("position BETWEEN 0 AND 9", name="position_range"),)

    template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("post_templates.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media_files.id", ondelete="RESTRICT"), index=True
    )

    template: Mapped[PostTemplate] = relationship(back_populates="media_items", lazy="raise")
    media: Mapped[MediaFile] = relationship(lazy="raise")
