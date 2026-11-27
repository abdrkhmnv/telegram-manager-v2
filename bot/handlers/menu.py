"""Bosh menyu, navigatsiya, /start, /help va eskirgan callback'lar."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import screens, texts
from bot.callbacks import NavCallback, Section
from bot.context import Services
from bot.rendering import show


async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    screen = screens.main_menu()
    await message.answer(screen.text, reply_markup=screen.markup)


async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    screen = screens.help_screen()
    await message.answer(screen.text, reply_markup=screen.markup)


async def on_navigate(
    callback: CallbackQuery,
    callback_data: NavCallback,
    svc: Services,
    state: FSMContext,
) -> None:
    section = callback_data.section
    await state.clear()
    if section is Section.STATUS:
        await callback.answer("Tekshirilmoqda…")
        status = await svc.status.collect()
        await show(callback, screens.status_screen(status, svc.timezone))
        return
    factory = screens.STATIC_SCREENS.get(section)
    await show(callback, factory() if factory is not None else screens.coming_soon(section))
    await callback.answer()


async def on_unknown_callback(callback: CallbackQuery) -> None:
    """Eski versiyadagi yoki buzilgan tugmalar: xavfsiz tarzda bosh menyuga qaytaradi."""
    await callback.answer(texts.EXPIRED_CALLBACK)
    await show(callback, screens.main_menu())


async def on_unknown_message(message: Message) -> None:
    await message.answer(texts.UNKNOWN_MESSAGE)


def build_router() -> Router:
    router = Router(name="menu")
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_help, Command("help"))
    router.callback_query.register(on_navigate, NavCallback.filter())
    # Quyidagilar oxirida — boshqa routerlar (keyingi bosqichlar) ulardan oldin ulanadi.
    router.callback_query.register(on_unknown_callback)
    router.message.register(on_unknown_message)
    return router
