"""Dispatcher'ni yig'ish: middleware'lar, routerlar, umumiy bog'liqliklar."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage

from bot.handlers.menu import build_router
from bot.middleware.callback_guard import CallbackGuardMiddleware
from bot.middleware.owner import OwnerOnlyMiddleware
from services.status_service import StatusService


def build_dispatcher(
    *,
    owner_id: int,
    storage: BaseStorage,
    status_service: StatusService,
    timezone: ZoneInfo,
) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    # Outer middleware — har qanday handler va filtrdan OLDIN, barcha update turlari uchun.
    dispatcher.update.outer_middleware(OwnerOnlyMiddleware(owner_id))
    dispatcher.callback_query.middleware(CallbackGuardMiddleware())
    dispatcher["status_service"] = status_service
    dispatcher["timezone"] = timezone
    dispatcher.include_router(build_router())
    return dispatcher
