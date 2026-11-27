"""Telethon klienti va Telegram xabarlari uchun soxta obyektlar (tarmoqsiz testlar)."""

from __future__ import annotations

import itertools
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def tg_message(
    message_id: int,
    text: str = "",
    *,
    photo_id: int | None = None,
    document_id: int | None = None,
    grouped_id: int | None = None,
    noforwards: bool = False,
) -> SimpleNamespace:
    photo = SimpleNamespace(id=photo_id) if photo_id is not None else None
    document = SimpleNamespace(id=document_id) if document_id is not None else None
    media = photo or document
    return SimpleNamespace(
        id=message_id,
        raw_text=text,
        message=text,
        text=text,
        media=media,
        photo=photo,
        document=document,
        video=None,
        gif=None,
        voice=None,
        audio=None,
        grouped_id=grouped_id,
        noforwards=noforwards,
    )


class FakeClient:
    """Telethon ``TelegramClient`` ning testlarda ishlatiladigan qismi."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, tuple[Any, ...], dict[str, Any]]] = []
        self.fail_for: dict[Any, list[BaseException]] = {}
        self.dialogs: list[Any] = []
        self._ids = itertools.count(5000)

    def _maybe_fail(self, peer: Any) -> None:
        errors = self.fail_for.get(peer)
        if errors:
            raise errors.pop(0)

    def _result(self) -> SimpleNamespace:
        return SimpleNamespace(id=next(self._ids))

    def sent_to(self, peer: Any) -> list[tuple[str, Any, tuple[Any, ...], dict[str, Any]]]:
        return [c for c in self.calls if c[1] == peer]

    async def send_message(self, peer: Any, message: Any = None, **kwargs: Any) -> Any:
        self._maybe_fail(peer)
        self.calls.append(("send_message", peer, (message,), kwargs))
        return self._result()

    async def send_file(self, peer: Any, file: Any, **kwargs: Any) -> Any:
        self._maybe_fail(peer)
        self.calls.append(("send_file", peer, (file,), kwargs))
        if isinstance(file, list):
            return [self._result() for _ in file]
        return self._result()

    async def forward_messages(self, peer: Any, messages: Any, **kwargs: Any) -> Any:
        self._maybe_fail(peer)
        self.calls.append(("forward_messages", peer, (messages,), kwargs))
        return [self._result() for _ in messages]

    async def edit_message(self, peer: Any, message_id: int, text: str, **kwargs: Any) -> Any:
        self._maybe_fail(peer)
        self.calls.append(("edit_message", peer, (message_id, text), kwargs))
        return self._result()

    async def delete_messages(self, peer: Any, message_ids: list[int], **kwargs: Any) -> Any:
        self._maybe_fail(peer)
        self.calls.append(("delete_messages", peer, (message_ids,), kwargs))
        return None

    async def iter_dialogs(self) -> Any:
        for dialog in self.dialogs:
            yield dialog

    def add_event_handler(self, *args: Any) -> None:
        self.calls.append(("add_event_handler", None, args, {}))

    def remove_event_handler(self, *args: Any) -> None:
        self.calls.append(("remove_event_handler", None, args, {}))


class FakeBot:
    """aiogram ``Bot.download`` o'rnini bosadi: file_id matnini faylga yozadi."""

    def __init__(self, payloads: dict[str, bytes] | None = None) -> None:
        self.payloads = payloads or {}

    async def download(self, file_id: str, destination: Path) -> None:
        Path(destination).write_bytes(self.payloads.get(file_id, file_id.encode()))  # noqa: ASYNC240


def entity(kind: str, entity_id: int, **attrs: Any) -> Any:
    """Telethon entity o'xshashi: klass nomi (User/Chat/Channel) muhim."""
    cls = type(kind, (), {})
    obj = cls()
    obj.id = entity_id
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj
