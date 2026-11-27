"""Inline klaviaturalar va umumiy tugma yordamchilari."""

from __future__ import annotations

from collections.abc import Callable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import texts
from bot.callbacks import NavCallback, Section

MAIN_MENU_ORDER: tuple[Section, ...] = (
    Section.SEND,
    Section.FORWARDER,
    Section.AUTOPOST,
    Section.RANDOM_POST,
    Section.MEDIA,
    Section.CHATS,
    Section.GROUPS,
    Section.CHANNELS,
    Section.SEARCH,
    Section.STATS,
    Section.SETTINGS,
    Section.HELP,
)

Row = list[InlineKeyboardButton]


def button(text: str, data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def nav_button(text: str, section: Section, page: int = 0) -> InlineKeyboardButton:
    return button(text, NavCallback(section=section, page=page))


def short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for section in MAIN_MENU_ORDER:
        builder.add(nav_button(texts.SECTION_TITLES[section], section))
    builder.adjust(2)
    return builder.as_markup()


def navigation_row(back_to: Section | None = None, back_page: int = 0) -> Row:
    row: Row = []
    if back_to is not None and back_to is not Section.HOME:
        row.append(nav_button(texts.BACK, back_to, back_page))
    row.append(nav_button(texts.HOME, Section.HOME))
    return row


def pager_row(page: int, pages: int, make: Callable[[int], CallbackData]) -> Row:
    """◀️ 2/5 ▶️ — faqat bir nechta sahifa bo'lsa."""
    if pages <= 1:
        return []
    row: Row = []
    if page > 0:
        row.append(button("◀️", make(page - 1)))
    row.append(button(f"{page + 1}/{pages}", make(page)))
    if page < pages - 1:
        row.append(button("▶️", make(page + 1)))
    return row


def markup(*rows: Row) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[row for row in rows if row])


def back_home(back_to: Section | None = None, back_page: int = 0) -> InlineKeyboardMarkup:
    return markup(navigation_row(back_to, back_page))


def confirm(yes: CallbackData, no: CallbackData, yes_text: str = "✅ Ha, tasdiqlayman") -> Row:
    return [button(yes_text, yes), button("❌ Bekor qilish", no)]


def settings_menu() -> InlineKeyboardMarkup:
    return markup(
        [nav_button(texts.STATUS_BUTTON, Section.STATUS)],
        [nav_button("🏷 Toifalar", Section.CATEGORIES)],
        [nav_button("📜 Yuborilgan xabarlar tarixi", Section.HISTORY)],
        navigation_row(),
    )


def status_menu() -> InlineKeyboardMarkup:
    return markup(
        [nav_button(texts.REFRESH, Section.STATUS)],
        navigation_row(Section.SETTINGS),
    )
