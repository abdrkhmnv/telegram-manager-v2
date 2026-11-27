"""Callback ma'lumotlari. Telegram chegarasi — 64 bayt; aiogram ``pack()`` da tekshiradi.

Prefikslar va maydon qiymatlari ataylab qisqa. ``id`` — bazadagi ichki ID
(Telegram ID emas), shuning uchun callback ma'lumoti hech qachon avtorizatsiya
yoki to'g'ridan-to'g'ri Telegram amali uchun ishlatilmaydi.
"""

from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData

CALLBACK_DATA_LIMIT = 64


class Section(StrEnum):
    """Panel bo'limlari."""

    HOME = "home"
    SEND = "send"
    HISTORY = "hist"
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
    CATEGORIES = "cats"
    STATUS = "status"
    HELP = "help"


class NavCallback(CallbackData, prefix="nav"):
    section: Section
    page: int = 0


class ChatCallback(CallbackData, prefix="ch"):
    """o=ochish, s=saqlash, k=toifalar, t=toifani almashtirish, n=yangi toifa, y=yangilash."""

    act: str
    id: int = 0
    sec: str = ""
    page: int = 0
    arg: int = 0


class CategoryCallback(CallbackData, prefix="ct"):
    """o=ochish, d=o'chirish (so'rov), x=o'chirishni tasdiqlash."""

    act: str
    id: int = 0


class PickCallback(CallbackData, prefix="pk"):
    """Chat tanlash: t=belgilash, p=sahifa, d=tayyor, x=bekor qilish."""

    act: str
    id: int = 0
    page: int = 0


class FlowCallback(CallbackData, prefix="fl"):
    """Ko'p bosqichli oqimlardagi tugmalar (rejim, takrorlanish, tasdiqlash...)."""

    act: str
    val: str = ""


class HistoryCallback(CallbackData, prefix="hs"):
    """o=ochish, e=tahrirlash, d=o'chirish (so'rov), x=o'chirishni tasdiqlash."""

    act: str
    id: int = 0
    page: int = 0


class RuleCallback(CallbackData, prefix="fr"):
    """o=ochish, p=pauza/davom, s=yoqish/o'chirib qo'yish, k=kalit so'zlar, m=media turlari,
    mt=media turini almashtirish, u=dublikat, h=sarlavha, t=izoh, l=loglar,
    d=o'chirish, x=tasdiqlash."""

    act: str
    id: int = 0
    arg: str = ""


class TaskCallback(CallbackData, prefix="tk"):
    """o=ochish, p=pauza/davom, c=bekor qilish, d=o'chirish, x=tasdiqlash, e=matnni tahrirlash."""

    act: str
    id: int = 0
    arg: int = 0


class MediaCallback(CallbackData, prefix="md"):
    """o=ochish, v=ko'rish, d=o'chirish, x=tasdiqlash."""

    act: str
    id: int = 0
    page: int = 0
