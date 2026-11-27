"""Avtorizatsiya: panel faqat bitta egaga tegishli."""

from __future__ import annotations


def is_owner(user_id: int | None, owner_id: int) -> bool:
    """Faqat aniq mos keladigan musbat ID egasi hisoblanadi.

    Callback ma'lumoti yoki xabar matni avtorizatsiya manbai EMAS — faqat
    Telegram serveri tomonidan berilgan yuboruvchi ID'si tekshiriladi.
    """
    if owner_id <= 0 or user_id is None:
        return False
    return user_id == owner_id
