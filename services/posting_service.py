"""Post shablonini kontentga aylantirish."""

from __future__ import annotations

from database.models import PostTemplate
from services.message_service import OutgoingContent


def template_content(template: PostTemplate) -> OutgoingContent:
    """Shablon ``media_items`` va ularning ``media`` si oldindan yuklangan bo'lishi kerak."""
    media = tuple(item.media for item in sorted(template.media_items, key=lambda i: i.position))
    return OutgoingContent(text=template.text, media=media)
