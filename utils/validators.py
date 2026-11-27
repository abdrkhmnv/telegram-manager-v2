"""Foydalanuvchi kiritgan ma'lumotlarni tekshirish.

Xatolik xabarlari o'zbek tilida, chunki ular to'g'ridan-to'g'ri boshqaruv
paneliga chiqariladi.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, time
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


_TIME_RE = re.compile(r"^\s*([01]?\d|2[0-3])[:.]([0-5]\d)\s*$")
_DATETIME_RE = re.compile(
    r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s+([01]?\d|2[0-3])[:.]([0-5]\d)\s*$"
)
_RANGE_RE = re.compile(r"^\s*(\d{1,5})\s*(?:[-–—]\s*(\d{1,5}))?\s*$")


def parse_time(value: str) -> time:
    """``"9:30"`` / ``"09.30"`` -> ``time(9, 30)``."""
    match = _TIME_RE.match(value)
    if not match:
        raise InputValidationError("Vaqt formati: SS:DD (masalan 09:30)")
    return time(int(match.group(1)), int(match.group(2)))


def parse_local_datetime(value: str) -> datetime:
    """``"27.11.2026 21:30"`` -> naive mahalliy ``datetime``."""
    match = _DATETIME_RE.match(value)
    if not match:
        raise InputValidationError("Format: KK.OO.YYYY SS:DD (masalan 28.11.2026 09:30)")
    day, month, year, hour, minute = (int(g) for g in match.groups())
    try:
        return datetime(year, month, day, hour, minute)  # noqa: DTZ001 — mahalliy vaqt
    except ValueError as exc:
        raise InputValidationError("Bunday sana mavjud emas") from exc


def parse_minutes_range(value: str) -> tuple[int, int]:
    """``"30-90"`` (daqiqa) -> ``(1800, 5400)`` soniya; ``"60"`` -> ``(3600, 3600)``."""
    match = _RANGE_RE.match(value)
    if not match:
        raise InputValidationError("Format: MIN-MAX daqiqa (masalan 30-90)")
    low = int(match.group(1))
    high = int(match.group(2) or low)
    return validate_interval(low * 60, high * 60)


def parse_hours_range(value: str) -> tuple[time | None, time | None]:
    """``"09:00-22:00"`` -> oyna; ``"0"`` -> kun bo'yi (``None, None``)."""
    text = value.strip()
    if text in {"0", "-", ""}:
        return None, None
    parts = re.split(r"\s*[-–—]\s*", text)
    if len(parts) != 2:
        raise InputValidationError("Format: SS:DD-SS:DD (masalan 09:00-22:00) yoki 0")
    start, end = parse_time(parts[0]), parse_time(parts[1])
    if start == end:
        return None, None
    return start, end
