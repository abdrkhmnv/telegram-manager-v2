"""Dispatcher'ni yig'ish: middleware'lar, routerlar, umumiy bog'liqliklar."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage

from bot import picker
from bot.context import Services
from bot.handlers import (
    autopost,
    chats,
    forwarder,
    history,
    media_stats,
    menu,
    random_post,
    send,
)
from bot.middleware.callback_guard import CallbackGuardMiddleware
from bot.middleware.owner import OwnerOnlyMiddleware
from bot.middleware.user_lock import UserLockMiddleware


def build_dispatcher(*, owner_id: int, storage: BaseStorage, services: Services) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    # Outer middleware — har qanday handler va filtrdan OLDIN, barcha update turlari uchun.
    dispatcher.update.outer_middleware(OwnerOnlyMiddleware(owner_id))
    dispatcher.callback_query.middleware(CallbackGuardMiddleware())
    dispatcher.message.middleware(UserLockMiddleware())
    dispatcher["svc"] = services
    # Tartib muhim: aniq handlerlar oldin, menu (umumiy va "eskirgan tugma") oxirida.
    for module in (picker, chats, send, history, forwarder, autopost, random_post, media_stats):
        dispatcher.include_router(module.build_router())
    dispatcher.include_router(menu.build_router())
    return dispatcher
