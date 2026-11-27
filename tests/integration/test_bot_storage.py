from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey

from bot.storage import PostgresStorage, build_storage_key
from database.connection import Database


class SendFlow(StatesGroup):
    choose_chat = State()


KEY = StorageKey(bot_id=1, chat_id=777, user_id=777)


async def test_state_and_data_survive_new_storage_instance(database: Database) -> None:
    storage = PostgresStorage(database)
    assert await storage.get_state(KEY) is None
    assert await storage.get_data(KEY) == {}

    await storage.set_state(KEY, SendFlow.choose_chat)
    await storage.set_data(KEY, {"targets": [-100, -200], "text": "Salom"})
    await storage.set_state(KEY, SendFlow.choose_chat)  # data saqlanib qolishi kerak

    restarted = PostgresStorage(database)
    assert await restarted.get_state(KEY) == SendFlow.choose_chat.state
    assert await restarted.get_data(KEY) == {"targets": [-100, -200], "text": "Salom"}

    await restarted.set_state(KEY, None)
    await restarted.set_data(KEY, {})
    assert await restarted.get_state(KEY) is None
    assert await restarted.get_data(KEY) == {}


async def test_update_data_merges(database: Database) -> None:
    storage = PostgresStorage(database)
    await storage.set_data(KEY, {"a": 1})
    await storage.update_data(KEY, {"b": 2})
    assert await storage.get_data(KEY) == {"a": 1, "b": 2}


def test_keys_are_isolated_per_user_and_destiny() -> None:
    other_user = StorageKey(bot_id=1, chat_id=777, user_id=778)
    other_destiny = StorageKey(bot_id=1, chat_id=777, user_id=777, destiny="other")
    keys = {build_storage_key(k) for k in (KEY, other_user, other_destiny)}
    assert len(keys) == 3
