"""💬 Chatlar, 👥 Guruhlar, 📢 Kanallar, 🔎 Qidiruv va 🏷 Toifalar."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import CategoryCallback, ChatCallback, NavCallback, Section
from bot.context import Services
from bot.keyboards import (
    Row,
    button,
    confirm,
    markup,
    navigation_row,
    pager_row,
    short,
)
from bot.rendering import show
from bot.screens import Screen
from bot.utils import CHAT_TYPE_LABELS, h, reply, when
from database.models import Chat
from database.repositories.categories import CategoryExistsError
from services.chat_service import SECTION_TYPES

LIST_SECTIONS = {Section.CHATS, Section.GROUPS, Section.CHANNELS}


class SearchStates(StatesGroup):
    query = State()


class CategoryStates(StatesGroup):
    name = State()


def chat_button(chat: Chat, sec: str, page: int) -> Row:
    label = ("⭐ " if chat.is_saved else "") + short(chat.title)
    return [button(label, ChatCallback(act="o", id=chat.id, sec=sec, page=page))]


async def chat_list_screen(svc: Services, section: Section, page: int, note: str = "") -> Screen:
    result = await svc.chats.page(SECTION_TYPES[section.value], page)
    lines = [f"<b>{texts.SECTION_TITLES[section]}</b> — {result.total} ta"]
    if note:
        lines.append(note)
    if result.total == 0:
        lines.append(
            "\nRo'yxat bo'sh. <b>🔄 Yangilash</b> tugmasini bosing — akkauntdagi "
            "dialoglar yuklanadi."
        )
    rows = [chat_button(chat, section.value, result.page) for chat in result.chats]
    rows.append(
        pager_row(result.page, result.pages, lambda p: NavCallback(section=section, page=p))
    )
    rows.append([button(texts.REFRESH, ChatCallback(act="y", sec=section.value))])
    rows.append(navigation_row())
    return Screen("\n".join(lines), markup(*rows))


def back_target(sec: str, page: int) -> Row:
    if sec == Section.CATEGORIES.value:
        return navigation_row(Section.CATEGORIES)
    try:
        return navigation_row(Section(sec), page)
    except ValueError:
        return navigation_row()


async def chat_detail_screen(svc: Services, chat_id: int, sec: str, page: int) -> Screen | None:
    chat = await svc.chats.get(chat_id)
    if chat is None:
        return None
    assigned = await svc.chats.chat_category_ids(chat_id)
    names = [c.name for c in await svc.chats.categories() if c.id in assigned]
    lines = [
        f"<b>{h(chat.title)}</b>",
        "",
        f"Turi: {CHAT_TYPE_LABELS[chat.chat_type]}",
        f"ID: <code>{chat.telegram_id}</code>",
        f"Username: @{h(chat.username)}" if chat.username else "Username: —",
        f"A'zolar: {chat.members_count}" if chat.members_count else "A'zolar: —",
        f"Saqlangan: {'⭐ ha' if chat.is_saved else 'yo‘q'}",
        f"Toifalar: {h(', '.join(names)) if names else '—'}",
        f"Holat: {'✅ ochiq' if chat.is_accessible else '⚠️ oxirgi yangilashda topilmadi'}",
        f"Yangilangan: {when(chat.last_synced_at, svc.timezone)}",
    ]
    save_text = "☆ Saqlanganlardan olish" if chat.is_saved else "⭐ Saqlash"
    rows = [
        [
            button(save_text, ChatCallback(act="s", id=chat.id, sec=sec, page=page)),
            button("🏷 Toifalar", ChatCallback(act="k", id=chat.id, sec=sec, page=page)),
        ],
        back_target(sec, page),
    ]
    return Screen("\n".join(lines), markup(*rows))


async def chat_categories_screen(svc: Services, chat_id: int, sec: str, page: int) -> Screen:
    categories = await svc.chats.categories()
    assigned = await svc.chats.chat_category_ids(chat_id)
    rows = [
        [
            button(
                ("✅ " if c.id in assigned else "▫️ ") + short(c.name),
                ChatCallback(act="t", id=chat_id, sec=sec, page=page, arg=c.id),
            )
        ]
        for c in categories
    ]
    rows.append([button("➕ Yangi toifa", ChatCallback(act="n", id=chat_id, sec=sec, page=page))])
    rows.append([button(texts.BACK, ChatCallback(act="o", id=chat_id, sec=sec, page=page))])
    text = "<b>🏷 Toifalar</b>\n\nBelgilash yoki olib tashlash uchun toifani bosing."
    if not categories:
        text += "\n\nHali toifa yo'q — ➕ Yangi toifa yarating."
    return Screen(text, markup(*rows))


# ------------------------------------------------------------------ handlers
async def on_list(
    callback: CallbackQuery, callback_data: NavCallback, svc: Services, state: FSMContext
) -> None:
    await state.clear()
    await show(callback, await chat_list_screen(svc, callback_data.section, callback_data.page))
    await callback.answer()


async def on_chat_action(
    callback: CallbackQuery, callback_data: ChatCallback, svc: Services, state: FSMContext
) -> None:
    data = callback_data
    if data.act == "y":
        await callback.answer("🔄 Dialoglar yuklanmoqda…")
        result = await svc.chats.sync_dialogs()
        note = f"✅ Yangilandi: {result.total} ta dialog."
        await show(callback, await chat_list_screen(svc, Section(data.sec), 0, note))
        return
    if data.act == "s":
        saved = await svc.chats.toggle_saved(data.id)
        await callback.answer("⭐ Saqlandi" if saved else "Saqlanganlardan olindi")
    elif data.act == "t":
        added = await svc.chats.toggle_category(data.id, data.arg)
        await callback.answer("Toifaga qo'shildi" if added else "Toifadan olindi")
        await show(callback, await chat_categories_screen(svc, data.id, data.sec, data.page))
        return
    elif data.act == "k":
        await callback.answer()
        await show(callback, await chat_categories_screen(svc, data.id, data.sec, data.page))
        return
    elif data.act == "n":
        await state.set_state(CategoryStates.name)
        await state.update_data(chat_id=data.id, sec=data.sec, page=data.page)
        await callback.answer()
        await show(
            callback,
            Screen(
                "Yangi toifa nomini yuboring (1–64 belgi).",
                markup(
                    [button("❌ Bekor qilish", ChatCallback(act="k", id=data.id, sec=data.sec))]
                ),
            ),
        )
        return
    else:
        await callback.answer()
    screen = await chat_detail_screen(svc, data.id, data.sec, data.page)
    if screen is None:
        await show(callback, Screen("Chat topilmadi.", markup(navigation_row())))
        return
    await show(callback, screen)


async def on_new_category_name(message: Message, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    try:
        await svc.chats.create_category(message.text or "", chat_id=chat_id)
    except CategoryExistsError:
        await message.answer("Bunday toifa allaqachon bor. Boshqa nom yuboring.")
        return
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    if chat_id:
        await reply(
            message,
            await chat_categories_screen(svc, chat_id, data.get("sec", ""), data.get("page", 0)),
        )
    else:
        await reply(message, await categories_screen(svc))


# ------------------------------------------------------------------ search
async def on_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchStates.query)
    await callback.answer()
    await show(
        callback,
        Screen(
            "<b>🔎 Qidiruv</b>\n\nChat nomi yoki @username'ning bir qismini yuboring.",
            markup(navigation_row()),
        ),
    )


async def on_search_query(message: Message, svc: Services) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Qidiruv so'zini matn ko'rinishida yuboring.")
        return
    result = await svc.chats.page(None, 0, query=query[:64], accessible_only=False)
    lines = [f"<b>🔎 «{h(query[:64])}»</b> — {result.total} ta natija"]
    if result.total > len(result.chats):
        lines.append(f"Birinchi {len(result.chats)} tasi ko'rsatildi — aniqroq so'z yuboring.")
    if result.total == 0:
        lines.append("Hech narsa topilmadi. Chatlar ro'yxatini 🔄 yangilab ko'ring.")
    rows = [chat_button(chat, Section.SEARCH.value, 0) for chat in result.chats]
    rows.append(navigation_row())
    await reply(message, Screen("\n".join(lines), markup(*rows)))


# --------------------------------------------------------------- categories
async def categories_screen(svc: Services) -> Screen:
    categories = await svc.chats.categories()
    rows = [[button("🏷 " + short(c.name), CategoryCallback(act="o", id=c.id))] for c in categories]
    rows.append([button("➕ Yangi toifa", CategoryCallback(act="n"))])
    rows.append(navigation_row(Section.SETTINGS))
    text = "<b>🏷 Toifalar</b>\n\nChatlarni toifalarga ajratish chat sahifasida bajariladi."
    if not categories:
        text += "\n\nHali toifa yo'q."
    return Screen(text, markup(*rows))


async def on_categories(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await show(callback, await categories_screen(svc))


async def on_category_action(
    callback: CallbackQuery, callback_data: CategoryCallback, svc: Services, state: FSMContext
) -> None:
    data = callback_data
    if data.act == "n":
        await state.set_state(CategoryStates.name)
        await state.update_data(chat_id=None)
        await callback.answer()
        await show(
            callback,
            Screen(
                "Yangi toifa nomini yuboring (1–64 belgi).",
                markup(navigation_row(Section.CATEGORIES)),
            ),
        )
        return
    if data.act == "x":
        deleted = await svc.chats.delete_category(data.id)
        await callback.answer("🗑 O'chirildi" if deleted else "Toifa allaqachon o'chirilgan")
        await show(callback, await categories_screen(svc))
        return
    category, chats = await svc.chats.category(data.id)
    await callback.answer()
    if category is None:
        await show(callback, await categories_screen(svc))
        return
    if data.act == "d":
        await show(
            callback,
            Screen(
                f"<b>🏷 {h(category.name)}</b> toifasini o'chirasizmi?\n"
                "Chatlarning o'zi o'chirilmaydi, faqat toifa olib tashlanadi.",
                markup(
                    confirm(
                        CategoryCallback(act="x", id=category.id),
                        CategoryCallback(act="o", id=category.id),
                    )
                ),
            ),
        )
        return
    lines = [f"<b>🏷 {h(category.name)}</b> — {len(chats)} ta chat"]
    rows = [chat_button(chat, Section.CATEGORIES.value, 0) for chat in chats]
    rows.append([button("🗑 O'chirish", CategoryCallback(act="d", id=category.id))])
    rows.append(navigation_row(Section.CATEGORIES))
    await show(callback, Screen("\n".join(lines), markup(*rows)))


def build_router() -> Router:
    router = Router(name="chats")
    router.callback_query.register(on_list, NavCallback.filter(F.section.in_(LIST_SECTIONS)))
    router.callback_query.register(on_search, NavCallback.filter(F.section == Section.SEARCH))
    router.callback_query.register(
        on_categories, NavCallback.filter(F.section == Section.CATEGORIES)
    )
    router.callback_query.register(on_chat_action, ChatCallback.filter())
    router.callback_query.register(on_category_action, CategoryCallback.filter())
    router.message.register(on_new_category_name, StateFilter(CategoryStates.name), F.text)
    router.message.register(on_search_query, StateFilter(SearchStates.query), F.text)
    return router
