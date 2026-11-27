"""📜 Yuborilgan xabarlar tarixi: ko'rish, tahrirlash, o'chirish (tasdiqlash bilan)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.callbacks import HistoryCallback, NavCallback, Section
from bot.content import message_html
from bot.context import Services
from bot.keyboards import button, confirm, markup, navigation_row, pager_row, short
from bot.rendering import show
from bot.screens import Screen
from bot.utils import h, reply, when
from utils.time_utils import format_local
from utils.validators import TELEGRAM_MESSAGE_LIMIT


class HistoryStates(StatesGroup):
    edit = State()


async def history_screen(svc: Services, page: int) -> Screen:
    items, page, pages = await svc.messages.history(page)
    lines = ["<b>📜 Yuborilgan xabarlar</b>"]
    if not items:
        lines.append("\nHali panel orqali xabar yuborilmagan.")
    rows = []
    for item in items:
        title = await svc.messages.chat_title(item.chat_telegram_id)
        stamp = format_local(item.created_at, svc.timezone, "%d.%m %H:%M")
        label = f"{stamp} · {short(title, 16)} · {short(item.preview or '—', 18)}"
        rows.append([button(label, HistoryCallback(act="o", id=item.id, page=page))])
    rows.append(pager_row(page, pages, lambda p: NavCallback(section=Section.HISTORY, page=p)))
    rows.append(navigation_row(Section.SETTINGS))
    return Screen("\n".join(lines), markup(*rows))


async def detail_screen(svc: Services, log_id: int, page: int) -> Screen:
    log = await svc.messages.get_log(log_id)
    if log is None:
        return Screen("Xabar topilmadi.", markup(navigation_row(Section.HISTORY, page)))
    title = await svc.messages.chat_title(log.chat_telegram_id)
    text = (
        f"<b>📜 Xabar</b>\n\nChat: {h(title)}\nYuborilgan: {when(log.created_at, svc.timezone)}\n"
        f"Xabar ID: <code>{log.message_id}</code>\n\n{h(log.preview or '—')}"
    )
    return Screen(
        text,
        markup(
            [
                button("✏️ Matnni tahrirlash", HistoryCallback(act="e", id=log_id, page=page)),
                button("🗑 O'chirish", HistoryCallback(act="d", id=log_id, page=page)),
            ],
            navigation_row(Section.HISTORY, page),
        ),
    )


async def on_history(
    callback: CallbackQuery, callback_data: NavCallback, svc: Services, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    await show(callback, await history_screen(svc, callback_data.page))


async def on_action(
    callback: CallbackQuery, callback_data: HistoryCallback, svc: Services, state: FSMContext
) -> None:
    data = callback_data
    if data.act == "e":
        await state.set_state(HistoryStates.edit)
        await state.update_data(log_id=data.id, page=data.page)
        await callback.answer()
        await show(
            callback,
            Screen(
                "Yangi matnni yuboring. Formatlash saqlanadi. Media xabarda izoh o'zgaradi.",
                markup(
                    [
                        button(
                            "❌ Bekor qilish", HistoryCallback(act="o", id=data.id, page=data.page)
                        )
                    ]
                ),
            ),
        )
        return
    if data.act == "d":
        await callback.answer()
        await show(
            callback,
            Screen(
                "🗑 Bu xabar chatdan <b>hamma uchun</b> o'chirilsinmi? "
                "Bu amalni qaytarib bo'lmaydi.",
                markup(
                    confirm(
                        HistoryCallback(act="x", id=data.id, page=data.page),
                        HistoryCallback(act="o", id=data.id, page=data.page),
                    )
                ),
            ),
        )
        return
    if data.act == "x":
        await callback.answer("O'chirilmoqda…")
        error = await svc.messages.delete(data.id)
        if error:
            await show(
                callback,
                Screen(
                    f"❌ O'chirilmadi: {h(error)}",
                    markup(navigation_row(Section.HISTORY, data.page)),
                ),
            )
            return
        await show(callback, await history_screen(svc, data.page))
        return
    await state.clear()
    await callback.answer()
    await show(callback, await detail_screen(svc, data.id, data.page))


async def on_new_text(message: Message, svc: Services, state: FSMContext) -> None:
    html_text = message_html(message)
    if not html_text:
        await message.answer("Yangi matnni matn ko'rinishida yuboring.")
        return
    if len(html_text) > TELEGRAM_MESSAGE_LIMIT:
        await message.answer(f"Matn juda uzun (ko'pi bilan {TELEGRAM_MESSAGE_LIMIT} belgi).")
        return
    data = await state.get_data()
    await state.clear()
    error = await svc.messages.edit(int(data["log_id"]), html_text)
    note = "✅ Tahrirlandi." if error is None else f"❌ Tahrirlanmadi: {h(error)}"
    await message.answer(note)
    await reply(message, await detail_screen(svc, int(data["log_id"]), int(data.get("page", 0))))


def build_router() -> Router:
    router = Router(name="history")
    router.callback_query.register(on_history, NavCallback.filter(F.section == Section.HISTORY))
    router.callback_query.register(on_action, HistoryCallback.filter())
    router.message.register(on_new_text, StateFilter(HistoryStates.edit))
    return router
