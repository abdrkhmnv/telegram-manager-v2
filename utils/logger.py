"""Tuzilmali (structured) loglash va maxfiy ma'lumotlarni yashirish.

Har bir log yozuvi chiqishdan oldin :class:`SecretRedactor` orqali o'tadi:
bot tokenlari, URL ichidagi parollar va ro'yxatdan o'tkazilgan maxfiy
qiymatlar (API hash, DB paroli) ``***`` bilan almashtiriladi.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_BOT_TOKEN_PATTERN = re.compile(r"\b\d{5,12}:[A-Za-z0-9_-]{30,64}\b")
_URL_PASSWORD_PATTERN = re.compile(r"(?P<prefix>[a-zA-Z][a-zA-Z0-9+.-]*://[^:/@\s]+:)[^@\s]+(?=@)")
_REDACTED = "***"
_MIN_SECRET_LENGTH = 4

# logging.LogRecord standart atributlari — qolganlari "extra" maydonlar hisoblanadi.
_STANDARD_RECORD_ATTRS = frozenset(
    vars(logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None)).keys()
) | {"message", "asctime", "taskName"}


class SecretRedactor:
    """Matndan maxfiy qiymatlarni olib tashlaydi (thread-safe)."""

    def __init__(self) -> None:
        self._literals: set[str] = set()
        self._lock = threading.Lock()

    def register(self, *values: str | None) -> None:
        with self._lock:
            for value in values:
                if value and len(value) >= _MIN_SECRET_LENGTH:
                    self._literals.add(value)

    def clear(self) -> None:
        with self._lock:
            self._literals.clear()

    def redact(self, text: str) -> str:
        with self._lock:
            literals = sorted(self._literals, key=len, reverse=True)
        for literal in literals:
            if literal in text:
                text = text.replace(literal, _REDACTED)
        text = _BOT_TOKEN_PATTERN.sub(_REDACTED, text)
        return _URL_PASSWORD_PATTERN.sub(lambda m: m.group("prefix") + _REDACTED, text)


redactor = SecretRedactor()


def register_secret(*values: str | None) -> None:
    """Maxfiy qiymatni loglarda yashiriladigan qilib ro'yxatga oladi."""
    redactor.register(*values)


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in vars(record).items()
        if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_")
    }


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redactor.redact(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact_value(v) for v in value]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return redactor.redact(str(value))


class JsonFormatter(logging.Formatter):
    """Har bir yozuvni bitta JSON qatori sifatida chiqaradi (UTC vaqt)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redactor.redact(record.getMessage()),
        }
        extras = _extra_fields(record)
        if extras:
            payload["extra"] = _redact_value(extras)
        if record.exc_info:
            payload["exc"] = redactor.redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Inson o'qishi uchun matnli format (maxfiy qiymatlar yashiriladi)."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S%z")

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        extras = _extra_fields(record)
        if extras:
            text += " " + json.dumps(extras, ensure_ascii=False, default=str)
        return redactor.redact(text)


def setup_logging(level: str = "INFO", fmt: str = "json", log_dir: Path | None = None) -> None:
    """Root loggerni sozlaydi. Bir necha marta chaqirilsa eski handlerlar almashtiriladi."""
    formatter: logging.Formatter = JsonFormatter() if fmt == "json" else TextFormatter()

    handlers: list[logging.Handler] = []
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    handlers.append(stream)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level.upper())

    # Shovqinli kutubxonalar loglarini cheklash.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
