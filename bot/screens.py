"""Ekranlar: (matn, klaviatura) juftligini qaytaruvchi sof funksiyalar."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup

from bot import keyboards, texts
from bot.callbacks import Section
from services.status_service import SystemStatus
from utils.time_utils import format_local


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    markup: InlineKeyboardMarkup


def main_menu() -> Screen:
    return Screen(texts.MAIN_MENU, keyboards.main_menu())


def help_screen() -> Screen:
    return Screen(texts.HELP, keyboards.back_home())


def settings_screen() -> Screen:
    return Screen(texts.SETTINGS, keyboards.settings_menu())


def coming_soon(section: Section) -> Screen:
    return Screen(texts.coming_soon(section), keyboards.back_home())


COMPONENT_LABELS = {
    "control_bot": "Control Bot",
    "forwarder": "Forwarder",
    "scheduler": "Rejalashtiruvchi (autopost)",
}


def _flag(ok: bool) -> str:
    return "✅" if ok else "❌"


def _duration(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} kun {hours} soat"
    if hours:
        return f"{hours} soat {minutes} daqiqa"
    return f"{minutes} daqiqa"


def status_screen(status: SystemStatus, tz: ZoneInfo) -> Screen:
    userbot = status.userbot
    if userbot.authorized:
        account = escape(userbot.display_name or "—")
        if userbot.username:
            account += f" (@{escape(userbot.username)})"
        account += f", ID <code>{userbot.user_id}</code>"
    else:
        account = "ulanmagan"
    revision = escape(status.migration_revision or "yo'q")
    lines = [
        "<b>ℹ️ Tizim holati</b>",
        "",
        f"{_flag(userbot.connected and userbot.authorized)} Userbot: {account}",
        f"{_flag(status.database_ok)} PostgreSQL",
        f"{_flag(status.migrations_current)} Migratsiya: {revision}",
        *(
            f"{_flag(ok)} {COMPONENT_LABELS.get(name, name)}"
            for name, ok in status.components.items()
        ),
        "",
        f"Versiya: {escape(status.version)}",
        f"Ishlamoqda: {_duration(status.uptime_seconds)}",
        f"Tekshirildi: {format_local(status.checked_at, tz)} ({escape(tz.key)})",
    ]
    return Screen("\n".join(lines), keyboards.status_menu())


STATIC_SCREENS = {
    Section.HOME: main_menu,
    Section.HELP: help_screen,
    Section.SETTINGS: settings_screen,
}
