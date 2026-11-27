"""Qayta ishlatiladigan chat tanlash (ko'p tanlovli) komponenti.

Tanlangan chatlar FSM ma'lumotida (``picked`` — bazadagi chat ID'lari) saqlanadi.
"Davom etish" bosilganda joriy FSM holati uchun ro'yxatdan o'tgan davom handler chaqiriladi.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery

from bot import screens, texts
from bot.callbacks import PickCallback
from bot.context import Services
from bot.keyboards import button, markup, pager_row, short
from bot.rendering import show
from bot.screens import Screen
from bot.utils import h
from database.models import ChatType

MAX_PICK = 50
TYPE_ICONS = {
    ChatType.PRIVATE: "👤",
    ChatType.GROUP: "👥",
    ChatType.SUPERGROUP: "👥",
    ChatType.CHANNEL: "📢",
}

DoneHandler = Callable[[CallbackQuery, Services, FSMContext], Awaitable[None]]
_done_handlers: dict[str, DoneHandler] = {}


def on_done(state: State, handler: DoneHandler) -> None:
    if state.state is None:
        raise ValueError("Holat StatesGroup ichida e'lon qilinishi kerak")
    _done_handlers[state.state] = handler


async def start_picker(
    callback: CallbackQuery,
    svc: Services,
    state: FSMContext,
    *,
    target: State,
    title: str,
    preselected: list[int] | None = None,
) -> None:
    await state.set_state(target)
    await state.update_data(picked=list(preselected or []), pick_page=0, pick_title=title)
    await show(callback, await picker_screen(svc, state))


async def picker_screen(svc: Services, state: FSMContext) -> Screen:
    data = await state.get_data()
    picked = set(data.get("picked", []))
    result = await svc.chats.page(None, int(data.get("pick_page", 0)))
    lines = [
        f"<b>{h(data.get('pick_title', 'Chatlarni tanlang'))}</b>",
        f"Tanlangan: {len(picked)} ta (ko'pi bilan {MAX_PICK})",
    ]
    if result.total == 0:
        lines.append("\nChatlar ro'yxati bo'sh. Avval 💬 Chatlar → 🔄 Yangilash ni bosing.")
    rows = [
        [
            button(
                ("✅ " if chat.id in picked else "▫️ ")
                + TYPE_ICONS.get(chat.chat_type, "")
                + " "
                + short(chat.title, 36),
                PickCallback(act="t", id=chat.id, page=result.page),
            )
        ]
        for chat in result.chats
    ]
    rows.append(pager_row(result.page, result.pages, lambda p: PickCallback(act="p", page=p)))
    rows.append(
        [
            button(f"➡️ Davom etish ({len(picked)})", PickCallback(act="d")),
            button("❌ Bekor qilish", PickCallback(act="x")),
        ]
    )
    return Screen("\n".join(lines), markup(*rows))


async def on_pick(
    callback: CallbackQuery, callback_data: PickCallback, svc: Services, state: FSMContext
) -> None:
    current = await state.get_state()
    if current not in _done_handlers:
        await callback.answer(texts.EXPIRED_CALLBACK)
        await show(callback, screens.main_menu())
        return
    act = callback_data.act
    if act == "x":
        await state.clear()
        await callback.answer("Bekor qilindi")
        await show(callback, screens.main_menu())
        return
    data = await state.get_data()
    picked: list[int] = list(data.get("picked", []))
    if act == "d":
        if not picked:
            await callback.answer("Kamida bitta chat tanlang", show_alert=True)
            return
        await callback.answer()
        await _done_handlers[current](callback, svc, state)
        return
    if act == "t":
        if callback_data.id in picked:
            picked.remove(callback_data.id)
        elif len(picked) >= MAX_PICK:
            await callback.answer(f"Ko'pi bilan {MAX_PICK} ta chat", show_alert=True)
            return
        else:
            picked.append(callback_data.id)
    await state.update_data(picked=picked, pick_page=callback_data.page)
    await callback.answer()
    await show(callback, await picker_screen(svc, state))


def build_router() -> Router:
    router = Router(name="picker")
    router.callback_query.register(on_pick, PickCallback.filter())
    return router
