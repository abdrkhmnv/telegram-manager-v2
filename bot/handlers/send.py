"""📤 Xabar yuborish: chatlarni tanlash → kontent → oldindan ko'rish → tasdiqlash → yuborish."""

from __future__ import annotations

import contextlib

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import picker, screens
from bot.callbacks import FlowCallback, NavCallback, Section
from bot.collect import collect, collected, summary, upsert_status
from bot.content import send_preview
from bot.context import Services
from bot.keyboards import Row, button, markup, navigation_row, short
from bot.rendering import show
from bot.screens import Screen
from bot.utils import h
from services.message_service import SendReport


class SendStates(StatesGroup):
    pick = State()
    content = State()
    confirm = State()


CONTENT_PROMPT = (
    "<b>📤 Xabar mazmuni</b>\n\n"
    "Matn, rasm, video, GIF, hujjat, audio yoki ovozli xabar yuboring. "
    "Bir nechta rasm/video yuborsangiz — albom bo'ladi (10 tagacha). "
    "Formatlash (qalin, kursiv, havola) saqlanadi."
)


def content_keyboard() -> Row:
    return [
        button("👁 Ko'rib chiqish", FlowCallback(act="preview")),
        button("❌ Bekor qilish", FlowCallback(act="cancel")),
    ]


async def on_start(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await picker.start_picker(
        callback, svc, state, target=SendStates.pick, title="📤 Qaysi chatlarga yuborilsin?"
    )


async def after_pick(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    await state.set_state(SendStates.content)
    await state.update_data(text=None, media=[], status_msg_id=None)
    await show(
        callback,
        Screen(CONTENT_PROMPT, markup([button("❌ Bekor qilish", FlowCallback(act="cancel"))])),
    )


async def on_content(message: Message, bot: Bot, svc: Services, state: FSMContext) -> None:
    error = await collect(message, bot, svc, state)
    if error:
        await message.answer(f"⚠️ {error}")
        return
    await upsert_status(
        message,
        bot,
        state,
        f"Qabul qilindi: {await summary(state)}.\n"
        "Yana qo'shishingiz yoki 👁 Ko'rib chiqish tugmasini bosishingiz mumkin.",
        markup(content_keyboard()),
    )


async def on_preview(callback: CallbackQuery, bot: Bot, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("text") and not data.get("media"):
        await callback.answer("Avval xabar mazmunini yuboring", show_alert=True)
        return
    await callback.answer()
    chats = await svc.messages.destinations(data.get("picked", []))
    if not chats:
        await state.clear()
        await show(callback, Screen("Tanlangan chatlar topilmadi.", markup(navigation_row())))
        return
    await send_preview(bot, callback.from_user.id, data.get("text"), data.get("media", []))
    await state.set_state(SendStates.confirm)
    titles = "\n".join(f"• {h(short(c.title))}" for c in chats[:15])
    more = f"\n… va yana {len(chats) - 15} ta" if len(chats) > 15 else ""
    text = (
        f"👆 Xabar shunday ko'rinadi.\n\n<b>{len(chats)} ta chatga yuborilsinmi?</b>\n"
        f"{titles}{more}"
    )
    rows = markup(
        [button(f"✅ Yuborish ({len(chats)})", FlowCallback(act="send"))],
        [
            button("✏️ Qayta yozish", FlowCallback(act="redo")),
            button("❌ Bekor qilish", FlowCallback(act="cancel")),
        ],
    )
    await bot.send_message(callback.from_user.id, text, reply_markup=rows)


async def on_redo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SendStates.content)
    await state.update_data(text=None, media=[], status_msg_id=None)
    await callback.answer()
    await show(
        callback,
        Screen(CONTENT_PROMPT, markup([button("❌ Bekor qilish", FlowCallback(act="cancel"))])),
    )


def report_text(report: SendReport) -> str:
    lines = [f"<b>📤 Natija</b>: ✅ {report.sent} ta yuborildi"]
    if report.failed:
        lines.append(f"❌ {len(report.failed)} ta yuborilmadi:")
        lines.extend(f"• {h(short(r.title))}: {h(r.error or '')}" for r in report.failed[:20])
    return "\n".join(lines)


async def on_send(callback: CallbackQuery, svc: Services, state: FSMContext) -> None:
    data = await state.get_data()
    content = await collected(svc, state)
    picked = list(data.get("picked", []))
    # Holat darhol tozalanadi: tugma qayta bosilsa, xabar ikkinchi marta yuborilmaydi.
    await state.clear()
    await callback.answer("Yuborish boshlandi")
    message = callback.message if isinstance(callback.message, Message) else None

    async def progress(done: int, total: int) -> None:
        if message is None:
            return
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(f"⏳ Yuborilmoqda: {done}/{total}")

    if message is not None:
        await message.edit_text(f"⏳ Yuborilmoqda: 0/{len(picked)}")
    report = await svc.messages.send(content, picked, progress=progress)
    await show(callback, Screen(report_text(report), screens.main_menu().markup))


async def on_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Bekor qilindi")
    await show(callback, screens.main_menu())


def build_router() -> Router:
    picker.on_done(SendStates.pick, after_pick)
    router = Router(name="send")
    router.callback_query.register(on_start, NavCallback.filter(F.section == Section.SEND))
    router.message.register(on_content, StateFilter(SendStates.content))
    router.callback_query.register(
        on_preview, StateFilter(SendStates.content), FlowCallback.filter(F.act == "preview")
    )
    router.callback_query.register(
        on_redo, StateFilter(SendStates.confirm), FlowCallback.filter(F.act == "redo")
    )
    router.callback_query.register(
        on_send, StateFilter(SendStates.confirm), FlowCallback.filter(F.act == "send")
    )
    router.callback_query.register(
        on_cancel,
        StateFilter(SendStates.pick, SendStates.content, SendStates.confirm),
        FlowCallback.filter(F.act == "cancel"),
    )
    return router
