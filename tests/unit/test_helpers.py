from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from utils.helpers import escape_like, sha256_file, sha256_text, truncate


def test_sha256_text_and_file_agree(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    data = b"x" * (3 * 1024 * 1024 + 7)  # bir nechta bo'lak
    path.write_bytes(data)
    assert sha256_file(path) == hashlib.sha256(data).hexdigest()
    assert sha256_text("salom") == hashlib.sha256(b"salom").hexdigest()


def test_truncate() -> None:
    assert truncate("abc", 5) == "abc"
    assert truncate("abcdef", 4) == "abc…"
    assert len(truncate("x" * 2000, 1000)) == 1000
    with pytest.raises(ValueError):
        truncate("abc", 0)


def test_escape_like() -> None:
    assert escape_like("50%_off\\") == "50\\%\\_off\\\\"
