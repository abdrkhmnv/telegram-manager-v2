"""Ilova konfiguratsiyasi (Pydantic Settings).

Sozlamalar uch mustaqil guruhga bo'lingan, shunda har bir buyruq faqat o'ziga
kerakli maxfiy ma'lumotlarni talab qiladi:

* :class:`AppSettings` — log, vaqt zonasi, saqlash katalogi.
* :class:`DatabaseSettings` — PostgreSQL ulanishi (migratsiyalar uchun ham yetarli).
* :class:`TelegramSettings` — Telethon va Control Bot (2-bosqichdan boshlab majburiy).

Barcha maxfiy qiymatlar ``SecretStr`` sifatida saqlanadi va xatolik
xabarlarida ko'rsatilmaydi (``hide_input_in_errors``).
"""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
    case_sensitive=False,
    hide_input_in_errors=True,
)

_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_BOT_TOKEN_RE = re.compile(r"^\d{5,12}:[A-Za-z0-9_-]{30,64}$")
_API_HASH_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ASYNC_PG_SCHEME = "postgresql+asyncpg://"


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


class AppSettings(BaseSettings):
    """Umumiy ilova sozlamalari."""

    model_config = _SETTINGS_CONFIG

    app_env: AppEnv = AppEnv.DEVELOPMENT
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON
    log_dir: Path | None = Path("logs")
    timezone: str = "Asia/Tashkent"
    storage_dir: Path = Path("storage")
    max_upload_size_mb: int = Field(default=50, ge=1, le=2000)

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, value: Any) -> str:
        level = str(value).strip().upper()
        if level not in _LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL quyidagilardan biri bo'lishi kerak: {sorted(_LOG_LEVELS)}")
        return level

    @field_validator("log_dir", mode="before")
    @classmethod
    def _empty_log_dir_is_none(cls, value: Any) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Noma'lum vaqt zonasi: {value}") from exc
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION


class DatabaseSettings(BaseSettings):
    """PostgreSQL ulanish sozlamalari."""

    model_config = _SETTINGS_CONFIG

    database_url: SecretStr
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_pool_timeout: float = Field(default=30.0, gt=0, le=300)
    db_connect_timeout: float = Field(default=10.0, gt=0, le=120)
    db_command_timeout: float = Field(default=30.0, gt=0, le=600)
    db_echo: bool = False

    @field_validator("database_url")
    @classmethod
    def _validate_url(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value().strip()
        if not url.startswith(_ASYNC_PG_SCHEME):
            raise ValueError(f"DATABASE_URL '{_ASYNC_PG_SCHEME}' bilan boshlanishi kerak")
        if len(url) <= len(_ASYNC_PG_SCHEME):
            raise ValueError("DATABASE_URL to'liq emas")
        return SecretStr(url)


class TelegramSettings(BaseSettings):
    """Telethon (MTProto) va Control Bot sozlamalari."""

    model_config = _SETTINGS_CONFIG

    telegram_api_id: int = Field(gt=0)
    telegram_api_hash: SecretStr
    bot_token: SecretStr
    owner_telegram_id: int = Field(gt=0)
    session_dir: Path = Path("storage/sessions")
    session_name: str = "userbot"

    @field_validator("telegram_api_hash")
    @classmethod
    def _validate_api_hash(cls, value: SecretStr) -> SecretStr:
        if not _API_HASH_RE.fullmatch(value.get_secret_value().strip()):
            raise ValueError("TELEGRAM_API_HASH 32 ta o'n oltilik belgidan iborat bo'lishi kerak")
        return SecretStr(value.get_secret_value().strip())

    @field_validator("bot_token")
    @classmethod
    def _validate_bot_token(cls, value: SecretStr) -> SecretStr:
        if not _BOT_TOKEN_RE.fullmatch(value.get_secret_value().strip()):
            raise ValueError("BOT_TOKEN formati noto'g'ri (kutilgan: 123456:ABC...)")
        return SecretStr(value.get_secret_value().strip())

    @field_validator("session_name")
    @classmethod
    def _validate_session_name(cls, value: str) -> str:
        if not _SESSION_NAME_RE.fullmatch(value):
            raise ValueError("SESSION_NAME faqat harf, raqam, '_' va '-' dan iborat bo'lishi kerak")
        return value

    @property
    def session_path(self) -> Path:
        return self.session_dir / self.session_name


def format_settings_error(exc: ValidationError) -> str:
    """Pydantic xatosini qiymatlarni oshkor qilmasdan o'qiladigan matnga aylantiradi."""
    lines = ["Konfiguratsiya xatosi (.env faylini tekshiring):"]
    for error in exc.errors(include_input=False, include_url=False):
        field = ".".join(str(part) for part in error.get("loc", ())) or "?"
        lines.append(f"  - {field.upper()}: {error.get('msg', 'noto‘g‘ri qiymat')}")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()  # type: ignore[call-arg]  # qiymatlar muhitdan o'qiladi


@lru_cache(maxsize=1)
def get_telegram_settings() -> TelegramSettings:
    return TelegramSettings()  # type: ignore[call-arg]  # qiymatlar muhitdan o'qiladi
