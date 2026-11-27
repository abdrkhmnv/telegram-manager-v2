from __future__ import annotations

import os
from pathlib import Path

import pytest

from utils.validators import (
    InputValidationError,
    normalize_username,
    parse_chat_reference,
    safe_storage_path,
    validate_interval,
    validate_keywords,
    validate_message_text,
)


class TestInterval:
    def test_valid(self) -> None:
        assert validate_interval(60, 3600) == (60, 3600)

    @pytest.mark.parametrize(("low", "high"), [(59, 100), (600, 60), (60, 8 * 24 * 3600)])
    def test_invalid(self, low: int, high: int) -> None:
        with pytest.raises(InputValidationError):
            validate_interval(low, high)


class TestChatReference:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("-1001234567890", -1001234567890),
            ("  777000 ", 777000),
            ("@durov", "durov"),
            ("durov_channel", "durov_channel"),
            ("https://t.me/durov", "durov"),
            ("t.me/Some_Channel/", "Some_Channel"),
        ],
    )
    def test_valid(self, raw: str, expected: int | str) -> None:
        assert parse_chat_reference(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["", "0", "@ab", "1abc", "https://t.me/+AbCdEf123", "t.me/joinchat/xyz", "bad name"],
    )
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(InputValidationError):
            parse_chat_reference(raw)

    def test_username_rules(self) -> None:
        assert normalize_username("@Valid_name1") == "Valid_name1"
        with pytest.raises(InputValidationError):
            normalize_username("_starts_with_underscore")


class TestKeywords:
    def test_strip_dedupe_preserve_order(self) -> None:
        assert validate_keywords([" Aksiya", "aksiya", "", "Chegirma "]) == ["Aksiya", "Chegirma"]

    def test_limits(self) -> None:
        with pytest.raises(InputValidationError):
            validate_keywords(["x" * 101])
        with pytest.raises(InputValidationError):
            validate_keywords([f"k{i}" for i in range(51)])


class TestMessageText:
    def test_caption_limit(self) -> None:
        assert validate_message_text("a" * 1024, caption=True)
        with pytest.raises(InputValidationError):
            validate_message_text("a" * 1025, caption=True)

    def test_blank_rejected(self) -> None:
        with pytest.raises(InputValidationError):
            validate_message_text("   ")


class TestSafeStoragePath:
    def test_inside(self, tmp_path: Path) -> None:
        assert safe_storage_path(tmp_path, "media/a.jpg") == tmp_path.resolve() / "media/a.jpg"

    @pytest.mark.parametrize("bad", ["../etc/passwd", "media/../../x", "/etc/passwd", "", "."])
    def test_escape_rejected(self, tmp_path: Path, bad: str) -> None:
        with pytest.raises(InputValidationError):
            safe_storage_path(tmp_path, bad)

    @pytest.mark.skipif(os.name == "nt", reason="symlink Windows'da huquq talab qiladi")
    def test_symlink_escape_rejected(self, tmp_path: Path) -> None:
        base = tmp_path / "storage"
        outside = tmp_path / "outside"
        base.mkdir()
        outside.mkdir()
        (base / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(InputValidationError):
            safe_storage_path(base, "link/secret.txt")
