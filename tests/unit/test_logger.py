from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest

from utils.logger import JsonFormatter, SecretRedactor, TextFormatter, redactor, register_secret

BOT_TOKEN = "123456:FAKE-token-for-tests-0000000000000"


@pytest.fixture(autouse=True)
def _clean_redactor() -> Iterator[None]:
    redactor.clear()
    yield
    redactor.clear()


def _emit(formatter: logging.Formatter, message: str, *args: object, **extra: object) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger(f"test.{id(formatter)}")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.info(message, *args, extra=extra)
    return stream.getvalue().strip()


class TestRedactor:
    def test_bot_token_pattern(self) -> None:
        assert BOT_TOKEN not in SecretRedactor().redact(f"token={BOT_TOKEN}")

    def test_url_password(self) -> None:
        text = SecretRedactor().redact("postgresql+asyncpg://user:s3cr3t@db:5432/x")
        assert text == "postgresql+asyncpg://user:***@db:5432/x"

    def test_registered_literal(self) -> None:
        r = SecretRedactor()
        r.register("0123456789abcdef0123456789abcdef", None, "ab")
        assert r.redact("hash=0123456789abcdef0123456789abcdef") == "hash=***"
        assert r.redact("ab stays") == "ab stays"  # juda qisqa qiymatlar ro'yxatga olinmaydi


class TestFormatters:
    def test_json_is_valid_and_redacted(self) -> None:
        register_secret("my-api-hash-value")
        line = _emit(JsonFormatter(), "connect %s", "my-api-hash-value", token=BOT_TOKEN, attempt=2)
        payload = json.loads(line)
        assert payload["level"] == "INFO"
        assert payload["message"] == "connect ***"
        assert payload["extra"] == {"token": "***", "attempt": 2}
        assert payload["ts"].endswith("+00:00")
        assert BOT_TOKEN not in line

    def test_json_exception_redacted(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("test.exc")
        logger.handlers = [handler]
        logger.propagate = False
        try:
            raise RuntimeError(f"bad token {BOT_TOKEN}")
        except RuntimeError:
            logger.exception("failed")
        assert BOT_TOKEN not in stream.getvalue()
        assert "RuntimeError" in json.loads(stream.getvalue())["exc"]

    def test_text_redacted(self) -> None:
        line = _emit(TextFormatter(), "url=%s", "postgresql://u:pw123@h/db")
        assert "pw123" not in line
        assert "INFO" in line
