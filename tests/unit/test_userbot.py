from __future__ import annotations

import asyncio
import stat
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("telethon")
pytest.importorskip("pydantic_settings")

from telethon.errors import FloodWaitError

from app.config import TelegramSettings
from core.login import interactive_login
from core.telegram_errors import with_flood_wait
from core.userbot import UserbotComponent, UserbotNotAuthorizedError


def make_settings(tmp_path: Path) -> TelegramSettings:
    return TelegramSettings(
        _env_file=None,
        telegram_api_id=12345,
        telegram_api_hash="0123456789abcdef0123456789abcdef",
        bot_token="123456:FAKE-token-for-tests-0000000000000",
        owner_telegram_id=777,
        session_dir=tmp_path / "sessions",
    )


def fake_client(*, authorized: bool, connected: bool = True) -> MagicMock:
    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=authorized)
    client.is_connected = MagicMock(return_value=connected)
    client.get_me = AsyncMock(
        return_value=MagicMock(id=777, first_name="Ali", last_name=None, username="ali")
    )
    client.start = AsyncMock()
    return client


def flood(seconds: int) -> FloodWaitError:
    return FloodWaitError(request=None, capture=seconds)


class TestUserbotComponent:
    async def test_not_authorized_stops_with_instruction(self, tmp_path: Path) -> None:
        client = fake_client(authorized=False)
        component = UserbotComponent(make_settings(tmp_path), client_factory=lambda _: client)
        with pytest.raises(UserbotNotAuthorizedError, match=r"main\.py login"):
            await component.start()
        client.disconnect.assert_awaited_once()

    async def test_authorized_start_status_stop(self, tmp_path: Path) -> None:
        settings = make_settings(tmp_path)
        client = fake_client(authorized=True)
        component = UserbotComponent(settings, client_factory=lambda _: client)
        assert component.status().connected is False

        await component.start()
        mode = stat.S_IMODE(settings.session_dir.stat().st_mode)
        assert mode == 0o700
        status = component.status()
        assert (status.connected, status.authorized, status.user_id) == (True, True, 777)
        assert status.display_name == "Ali"
        assert status.username == "ali"

        await component.stop()
        client.disconnect.assert_awaited_once()

    async def test_session_file_permissions_tightened(self, tmp_path: Path) -> None:
        settings = make_settings(tmp_path)
        settings.session_dir.mkdir(parents=True)
        session_file = settings.session_dir / "userbot.session"
        session_file.write_bytes(b"x")
        session_file.chmod(0o644)
        component = UserbotComponent(
            settings, client_factory=lambda _: fake_client(authorized=True)
        )
        await component.start()
        await component.stop()
        assert stat.S_IMODE(session_file.stat().st_mode) == 0o600

    async def test_watchdog_reconnects(self, tmp_path: Path) -> None:
        client = fake_client(authorized=True, connected=False)
        component = UserbotComponent(
            make_settings(tmp_path), client_factory=lambda _: client, watchdog_interval=0.01
        )
        await component.start()
        await asyncio.sleep(0.05)
        await component.stop()
        assert client.connect.await_count >= 2  # boshlang'ich + qayta ulanish

    def test_client_before_start_raises(self, tmp_path: Path) -> None:
        component = UserbotComponent(make_settings(tmp_path))
        with pytest.raises(RuntimeError):
            _ = component.client


class TestFloodWait:
    async def test_retries_after_short_wait(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr("core.telegram_errors.asyncio.sleep", fake_sleep)
        call = AsyncMock(side_effect=[flood(5), "ok"])
        assert await with_flood_wait(call) == "ok"
        assert sleeps == [6]

    async def test_long_wait_is_not_awaited(self) -> None:
        call = AsyncMock(side_effect=flood(3600))
        with pytest.raises(FloodWaitError):
            await with_flood_wait(call, max_wait=300)
        assert call.await_count == 1

    async def test_bounded_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("core.telegram_errors.asyncio.sleep", AsyncMock())
        call = AsyncMock(side_effect=flood(1))
        with pytest.raises(FloodWaitError):
            await with_flood_wait(call, retries=2)
        assert call.await_count == 3

    async def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError):
            await with_flood_wait(AsyncMock(), retries=-1)


class TestLogin:
    async def test_login_uses_prompts_and_never_returns_secrets(self, tmp_path: Path) -> None:
        client = fake_client(authorized=False)
        prompts: list[str] = []

        def fake_input(prompt: str) -> str:
            prompts.append(prompt)
            return "+998901234567"

        name = await interactive_login(
            make_settings(tmp_path),
            input_fn=fake_input,
            password_fn=lambda _: "secret",
            client_factory=lambda _: client,
        )
        assert name == "Ali"
        kwargs: dict[str, Any] = client.start.await_args.kwargs
        assert kwargs["phone"]() == "+998901234567"
        assert kwargs["password"]() == "secret"
        client.disconnect.assert_awaited_once()

    async def test_already_authorized_skips_prompts(self, tmp_path: Path) -> None:
        client = fake_client(authorized=True)
        await interactive_login(make_settings(tmp_path), client_factory=lambda _: client)
        client.start.assert_not_awaited()
