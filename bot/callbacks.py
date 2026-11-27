"""Callback ma'lumotlari. Telegram chegarasi — 64 bayt; aiogram ``pack()`` da tekshiradi."""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData

CALLBACK_DATA_LIMIT = 64


class Section(StrEnum):
    """Panel bo'limlari. Qiymatlar qisqa — callback_data chegarasini tejash uchun."""

    HOME = "home"
    SEND = "send"
    FORWARDER = "fwd"
    AUTOPOST = "ap"
    RANDOM_POST = "rap"
    MEDIA = "media"
    CHATS = "chats"
    GROUPS = "groups"
    CHANNELS = "chans"
    SEARCH = "search"
    STATS = "stats"
    SETTINGS = "set"
    STATUS = "status"
    HELP = "help"


class NavCallback(CallbackData, prefix="nav"):
    section: Section
    page: int = 0
