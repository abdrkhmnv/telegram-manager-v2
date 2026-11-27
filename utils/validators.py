"""Foydalanuvchi kiritgan ma'lumotlarni tekshirish.

Xatolik xabarlari o'zbek tilida, chunki ular to'g'ridan-to'g'ri boshqaruv
paneliga chiqariladi.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_CAPTION_LIMIT = 1024
MIN_INTERVAL_SECONDS = 60
MAX_INTERVAL_SECONDS = 7 * 24 * 3600
_MAX_BIGINT = 2**63 - 1

_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_NUMERIC_ID_RE = re.compile(r"^-?\d{1,19}$")
_PUBLIC_LINK_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?P<name>[A-Za-z0-9_]+)/?$",
    re.IGNORECASE,
)
_INVITE_LINK_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)", re.IGNORECASE
)


class InputValidationError(ValueError):
    """Foydalanuvchiga ko'rsatiladigan tekshiruv xatosi."""


def validate_interval(min_seconds: int, max_seconds: int) -> tuple[int, int]:
    if min_seconds < MIN_INTERVAL_SECONDS:
        raise InputValidationError(
            f"Minimal interval kamida {MIN_INTERVAL_SECONDS} soniya bo'lishi kerak"
        )
    if max_seconds > MAX_INTERVAL_SECONDS:
        raise InputValidationError("Maksimal interval 7 kundan oshmasligi kerak")
    if max_seconds < min_seconds:
        raise InputValidationError("Maksimal interval minimaldan kichik bo'lmasligi kerak")
    return min_seconds, max_seconds


def normalize_username(value: str) -> str:
    username = value.strip().removeprefix("@")
    if not _USERNAME_RE.fullmatch(username):
        raise InputValidationError(
            "Username noto'g'ri: 5-32 belgi, harf bilan boshlanadi, faqat harf, raqam va '_'"
        )
    return username


def parse_chat_reference(value: str) -> int | str:
    """Chat ID, @username yoki ochiq t.me havolasini ajratib oladi.

    Yopiq taklif havolalari (t.me/+..., joinchat) ataylab qabul qilinmaydi:
    tizim faqat akkauntga allaqachon ochiq bo'lgan chatlar bilan ishlaydi.
    """
    text = value.strip()
    if not text:
        raise InputValidationError("Chat ko'rsatilmagan")
    if _NUMERIC_ID_RE.fullmatch(text):
        chat_id = int(text)
        if chat_id == 0 or abs(chat_id) > _MAX_BIGINT:
            raise InputValidationError("Chat ID noto'g'ri")
        return chat_id
    if _INVITE_LINK_RE.match(text):
        raise InputValidationError(
            "Taklif havolalari qo'llab-quvvatlanmaydi. Chatga avval akkaunt orqali qo'shiling."
        )
    link = _PUBLIC_LINK_RE.fullmatch(text)
    if link:
        return normalize_username(link.group("name"))
    return normalize_username(text)


def validate_keywords(
    keywords: Iterable[str], *, max_items: int = 50, max_length: int = 100
) -> list[str]:
    """Kalit so'zlarni tozalaydi: bo'shliqlar, takrorlar (katta-kichik harfsiz) olib tashlanadi."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in keywords:
        keyword = raw.strip()
        if not keyword:
            continue
        if len(keyword) > max_length:
            raise InputValidationError(f"Kalit so'z {max_length} belgidan oshmasligi kerak")
        folded = keyword.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        result.append(keyword)
    if len(result) > max_items:
        raise InputValidationError(f"Kalit so'zlar soni {max_items} tadan oshmasligi kerak")
    return result


def validate_message_text(text: str, *, caption: bool = False) -> str:
    limit = TELEGRAM_CAPTION_LIMIT if caption else TELEGRAM_MESSAGE_LIMIT
    if not text.strip():
        raise InputValidationError("Matn bo'sh bo'lmasligi kerak")
    if len(text) > limit:
        raise InputValidationError(f"Matn {limit} belgidan oshmasligi kerak (hozir: {len(text)})")
    return text


def safe_storage_path(base_dir: Path, relative: str | Path) -> Path:
    """``relative`` yo'lni ``base_dir`` ichida qolishini kafolatlab qaytaradi.

    Mutlaq yo'llar, ``..`` orqali chiqish va katalogdan tashqariga olib
    chiquvchi symlinklar rad etiladi.
    """
    relative_path = Path(relative)
    if relative_path.is_absolute() or not str(relative).strip():
        raise InputValidationError("Fayl yo'li nisbiy bo'lishi kerak")
    base = base_dir.resolve()
    target = (base / relative_path).resolve()
    if target == base or not target.is_relative_to(base):
        raise InputValidationError("Fayl yo'li ruxsat etilgan saqlash katalogidan tashqarida")
    return target
