"""Vaqt bilan ishlash yordamchilari.

Qoidalar:
* Ma'lumotlar bazasida va ichki mantiqda faqat UTC (timezone-aware) vaqt ishlatiladi.
* Foydalanuvchiga ko'rsatishda va kiritishda mahalliy zona (standart: Asia/Tashkent).
* Naive ``datetime`` qabul qilinmaydi — bu jim xatolarning oldini oladi.

Hafta kunlari bitmaskasi: dushanba = 1 (bit 0), ..., yakshanba = 64 (bit 6).
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Tashkent"
DISPLAY_FORMAT = "%d.%m.%Y %H:%M"
ALL_WEEKDAYS_MASK = 0b1111111
WEEKDAY_NAMES_UZ = (
    "Dushanba",
    "Seshanba",
    "Chorshanba",
    "Payshanba",
    "Juma",
    "Shanba",
    "Yakshanba",
)

_system_random = random.SystemRandom()


@lru_cache(maxsize=16)
def get_timezone(name: str = DEFAULT_TIMEZONE) -> ZoneInfo:
    return ZoneInfo(name)


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Aware vaqtni UTC ga o'tkazadi; naive vaqt uchun ``ValueError``."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Naive datetime qabul qilinmaydi: vaqt zonasi ko'rsatilishi shart")
    return value.astimezone(UTC)


def to_local(value: datetime, tz: ZoneInfo) -> datetime:
    return ensure_utc(value).astimezone(tz)


def local_to_utc(local_value: datetime, tz: ZoneInfo) -> datetime:
    """Mahalliy (naive) vaqtni UTC ga o'tkazadi.

    DST bo'lgan zonalarda mavjud bo'lmagan vaqt (soat oldinga surilgan oraliq)
    o'tishdan keyingi birinchi haqiqiy lahzaga to'g'ri keladi. Asia/Tashkent'da DST yo'q.
    """
    if local_value.tzinfo is not None:
        raise ValueError("local_to_utc naive (mahalliy) vaqt kutadi")
    return local_value.replace(tzinfo=tz).astimezone(UTC)


def format_local(value: datetime, tz: ZoneInfo, fmt: str = DISPLAY_FORMAT) -> str:
    return to_local(value, tz).strftime(fmt)


def weekdays_to_mask(weekdays: Iterable[int]) -> int:
    """``[0, 2, 4]`` (dush, chor, juma) -> bitmaska."""
    mask = 0
    for day in weekdays:
        if not 0 <= day <= 6:
            raise ValueError(f"Hafta kuni 0..6 oralig'ida bo'lishi kerak, berilgan: {day}")
        mask |= 1 << day
    if mask == 0:
        raise ValueError("Kamida bitta hafta kuni tanlanishi kerak")
    return mask


def mask_to_weekdays(mask: int) -> list[int]:
    if not 1 <= mask <= ALL_WEEKDAYS_MASK:
        raise ValueError(f"Hafta kunlari maskasi 1..{ALL_WEEKDAYS_MASK} oralig'ida bo'lishi kerak")
    return [day for day in range(7) if mask & (1 << day)]


def _candidate(day: date, at: time, tz: ZoneInfo) -> datetime:
    return local_to_utc(datetime.combine(day, at), tz)


def next_daily_run(after: datetime, at: time, tz: ZoneInfo) -> datetime:
    """``after`` dan qat'iy keyingi, mahalliy ``at`` vaqtiga to'g'ri keladigan lahza (UTC)."""
    after_utc = ensure_utc(after)
    start_day = to_local(after_utc, tz).date()
    for offset in range(3):
        candidate = _candidate(start_day + timedelta(days=offset), at, tz)
        if candidate > after_utc:
            return candidate
    raise RuntimeError("Keyingi kunlik vaqtni hisoblab bo'lmadi")  # pragma: no cover


def next_weekly_run(after: datetime, at: time, weekdays_mask: int, tz: ZoneInfo) -> datetime:
    """Tanlangan hafta kunlaridagi keyingi ``at`` lahzasi (UTC)."""
    allowed = set(mask_to_weekdays(weekdays_mask))
    after_utc = ensure_utc(after)
    start_day = to_local(after_utc, tz).date()
    for offset in range(9):
        day = start_day + timedelta(days=offset)
        if day.weekday() not in allowed:
            continue
        candidate = _candidate(day, at, tz)
        if candidate > after_utc:
            return candidate
    raise RuntimeError("Keyingi haftalik vaqtni hisoblab bo'lmadi")  # pragma: no cover


def is_within_active_hours(moment: time, start: time | None, end: time | None) -> bool:
    """Faol soatlar oynasini tekshiradi. ``start > end`` bo'lsa oyna yarim tundan o'tadi.

    ``start`` yoki ``end`` berilmagan, yoki ular teng bo'lsa — kun bo'yi faol.
    Oyna ``[start, end)`` ko'rinishida: boshlanishi kiradi, oxiri kirmaydi.
    """
    if start is None or end is None or start == end:
        return True
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


def next_random_run(
    after: datetime,
    min_seconds: int,
    max_seconds: int,
    tz: ZoneInfo,
    active_from: time | None = None,
    active_to: time | None = None,
    rng: random.Random | None = None,
) -> datetime:
    """Foydalanuvchi belgilagan [min, max] oralig'ida tasodifiy keyingi vaqt.

    Agar natija faol soatlardan tashqariga tushsa, keyingi faol oyna boshlanishiga
    suriladi. Interval chegaralari :func:`utils.validators.validate_interval` da tekshiriladi.
    """
    if min_seconds <= 0 or max_seconds < min_seconds:
        raise ValueError("Interval noto'g'ri: 0 < min <= max bo'lishi kerak")
    generator = rng if rng is not None else _system_random
    delay = generator.randint(min_seconds, max_seconds)
    candidate = ensure_utc(after) + timedelta(seconds=delay)
    local_time = to_local(candidate, tz).time()
    if active_from is None or is_within_active_hours(local_time, active_from, active_to):
        return candidate
    return next_daily_run(candidate, active_from, tz)
