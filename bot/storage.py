"""aiogram FSM holatini PostgreSQL'da saqlash — ilova qayta ishga tushganda ham saqlanib qoladi."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.connection import Database
from database.models import BotState


def build_storage_key(key: StorageKey) -> str:
    parts = [
        str(key.bot_id),
        str(key.chat_id),
        str(key.user_id),
        str(getattr(key, "thread_id", None) or ""),
        str(getattr(key, "business_connection_id", None) or ""),
        str(key.destiny),
    ]
    return ":".join(parts)


class PostgresStorage(BaseStorage):
    """``bot_fsm_states`` jadvalidagi FSM saqlovchi.

    ``data`` JSON'ga aylantiriladigan bo'lishi kerak (str, int, list, dict ...).
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        statement = pg_insert(BotState).values(key=build_storage_key(key), state=value, data={})
        statement = statement.on_conflict_do_update(
            index_elements=[BotState.key],
            set_={"state": statement.excluded["state"], "updated_at": func.now()},
        )
        async with self._database.session() as session:
            await session.execute(statement)

    async def get_state(self, key: StorageKey) -> str | None:
        async with self._database.session() as session:
            return await session.scalar(
                select(BotState.state).where(BotState.key == build_storage_key(key))
            )

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        statement = pg_insert(BotState).values(key=build_storage_key(key), data=dict(data))
        statement = statement.on_conflict_do_update(
            index_elements=[BotState.key],
            set_={"data": statement.excluded["data"], "updated_at": func.now()},
        )
        async with self._database.session() as session:
            await session.execute(statement)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self._database.session() as session:
            data = await session.scalar(
                select(BotState.data).where(BotState.key == build_storage_key(key))
            )
        return dict(data) if data else {}

    async def close(self) -> None:
        """Baza ulanishi lifecycle tomonidan yopiladi."""
