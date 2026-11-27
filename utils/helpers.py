"""Umumiy kichik yordamchi funksiyalar."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_text(text: str) -> str:
    """Matnning SHA-256 xeshi (takroriy kontentni aniqlash uchun)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Faylni bo'laklab o'qib SHA-256 xeshini hisoblaydi (katta fayllar xotirani to'ldirmaydi)."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def truncate(text: str, limit: int) -> str:
    """Matnni ``limit`` belgigacha qisqartiradi (oxiriga "…" qo'yiladi)."""
    if limit < 1:
        raise ValueError("limit musbat bo'lishi kerak")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def escape_like(value: str, escape_char: str = "\\") -> str:
    """SQL LIKE/ILIKE uchun ``%`` va ``_`` belgilarini ekranlaydi."""
    return (
        value.replace(escape_char, escape_char * 2)
        .replace("%", f"{escape_char}%")
        .replace("_", f"{escape_char}_")
    )
