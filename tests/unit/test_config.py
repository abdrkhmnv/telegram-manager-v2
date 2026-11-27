from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pydantic_settings")

from pydantic import ValidationError

from app.config import (
    AppEnv,
    AppSettings,
    DatabaseSettings,
    TelegramSettings,
    format_settings_error,
)

DB_URL = "postgresql+asyncpg://user:super-secret-pw@localhost:5432/db"
VALID_TELEGRAM = {
    "telegram_api_id": 12345,
    "telegram_api_hash": "0123456789abcdef0123456789abcdef",
    "bot_token": "123456:FAKE-token-for-tests-0000000000000",
    "owner_telegram_id": 987654321,
}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Haqiqiy .env yoki muhit o'zgaruvchilari testlarga ta'sir qilmasin."""
    monkeypatch.chdir(tmp_path)
    for name in (
        "DATABASE_URL",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "BOT_TOKEN",
        "OWNER_TELEGRAM_ID",
        "LOG_LEVEL",
        "LOG_DIR",
        "TIMEZONE",
        "APP_ENV",
    ):
        monkeypatch.delenv(name, raising=False)


class TestAppSettings:
    def test_defaults(self) -> None:
        settings = AppSettings(_env_file=None)
        assert settings.timezone == "Asia/Tashkent"
        assert settings.tz.key == "Asia/Tashkent"
        assert settings.app_env is AppEnv.DEVELOPMENT
        assert settings.max_upload_size_bytes == 50 * 1024 * 1024

    def test_env_overrides_and_normalization(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "debug")
        monkeypatch.setenv("LOG_DIR", "")
        monkeypatch.setenv("APP_ENV", "production")
        settings = AppSettings(_env_file=None)
        assert settings.log_level == "DEBUG"
        assert settings.log_dir is None
        assert settings.is_production

    @pytest.mark.parametrize(
        ("field", "value"),
        [("log_level", "LOUD"), ("timezone", "Mars/Olympus"), ("max_upload_size_mb", 0)],
    )
    def test_invalid(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            AppSettings(_env_file=None, **{field: value})

    def test_reads_dotenv_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# izoh\nTIMEZONE=UTC\nLOG_FORMAT=text\n", encoding="utf-8")
        settings = AppSettings(_env_file=env_file)
        assert settings.timezone == "UTC"
        assert settings.log_format.value == "text"


class TestDatabaseSettings:
    def test_valid(self) -> None:
        settings = DatabaseSettings(_env_file=None, database_url=DB_URL)
        assert settings.database_url.get_secret_value() == DB_URL
        assert "super-secret-pw" not in repr(settings)

    def test_required(self) -> None:
        with pytest.raises(ValidationError):
            DatabaseSettings(_env_file=None)

    @pytest.mark.parametrize(
        "url", ["postgresql://u:p@h/db", "sqlite:///x.db", "postgresql+asyncpg://"]
    )
    def test_rejects_wrong_driver(self, url: str) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DatabaseSettings(_env_file=None, database_url=url)
        assert "u:p" not in str(excinfo.value)
        assert "u:p" not in format_settings_error(excinfo.value)

    def test_pool_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DatabaseSettings(_env_file=None, database_url=DB_URL, db_pool_size=0)


class TestTelegramSettings:
    def test_valid(self) -> None:
        settings = TelegramSettings(_env_file=None, **VALID_TELEGRAM)
        assert settings.owner_telegram_id == 987654321
        assert settings.session_path == Path("storage/sessions/userbot")
        assert VALID_TELEGRAM["bot_token"] not in repr(settings)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("telegram_api_hash", "not-a-hash"),
            ("bot_token", "12345"),
            ("owner_telegram_id", 0),
            ("telegram_api_id", -1),
            ("session_name", "../escape"),
        ],
    )
    def test_invalid(self, field: str, value: object) -> None:
        data = {**VALID_TELEGRAM, field: value}
        with pytest.raises(ValidationError) as excinfo:
            TelegramSettings(_env_file=None, **data)
        assert field.upper() in format_settings_error(excinfo.value)

    def test_missing_owner_is_error(self) -> None:
        data = {k: v for k, v in VALID_TELEGRAM.items() if k != "owner_telegram_id"}
        with pytest.raises(ValidationError):
            TelegramSettings(_env_file=None, **data)
