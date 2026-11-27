"""Inline klaviaturalar."""

from __future__ import annotations

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


def nav_button(text: str, section: Section, page: int = 0) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=NavCallback(section=section, page=page).pack()
    )


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for section in MAIN_MENU_ORDER:
        builder.add(nav_button(texts.SECTION_TITLES[section], section))
    builder.adjust(2)
    return builder.as_markup()


def navigation_row(back_to: Section | None = None) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if back_to is not None and back_to is not Section.HOME:
        row.append(nav_button(texts.BACK, back_to))
    row.append(nav_button(texts.HOME, Section.HOME))
    return row


def back_home(back_to: Section | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[navigation_row(back_to)])


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [nav_button(texts.STATUS_BUTTON, Section.STATUS)],
            navigation_row(),
        ]
    )


def status_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [nav_button(texts.REFRESH, Section.STATUS)],
            navigation_row(Section.SETTINGS),
        ]
    )
