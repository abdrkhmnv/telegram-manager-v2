"""Bir martalik interaktiv kirish: Telethon sessiyasini yaratadi.

Telefon raqami, tasdiqlash kodi va 2FA paroli faqat terminalda so'raladi,
hech qayerga (log, baza) yozilmaydi. Sessiya fayli ``600`` ruxsat bilan saqlanadi.
"""

from __future__ import annotations

import getpass
from collections.abc import Callable
from typing import Any

from app.config import TelegramSettings
from core.userbot import build_client, secure_session_dir, secure_session_file

InputFn = Callable[[str], str]


async def interactive_login(
    settings: TelegramSettings,
    *,
    input_fn: InputFn = input,
    password_fn: InputFn = getpass.getpass,
    client_factory: Callable[[TelegramSettings], Any] = build_client,
) -> str:
    """Kirishni bajaradi va akkaunt nomini qaytaradi."""
    secure_session_dir(settings.session_dir)
    client = client_factory(settings)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.start(
                phone=lambda: input_fn("Telefon raqam (+998...): ").strip(),
                code_callback=lambda: input_fn("Telegram yuborgan kod: ").strip(),
                password=lambda: password_fn("Ikki bosqichli tekshiruv paroli: "),
                max_attempts=3,
            )
        me = await client.get_me()
    finally:
        await client.disconnect()
        secure_session_file(settings.session_path)
    name = " ".join(p for p in (getattr(me, "first_name", ""), getattr(me, "last_name", "")) if p)
    return name or str(getattr(me, "id", ""))
