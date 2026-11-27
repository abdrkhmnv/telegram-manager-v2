"""Media fayllarni xavfsiz saqlash: hajm/MIME tekshiruvi, SHA-256 dedup, tozalash."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from database.connection import Database
from database.models import MediaFile, MediaType
from database.repositories.media import MediaRepository
from utils.helpers import sha256_file
from utils.logger import get_logger
from utils.validators import InputValidationError, safe_storage_path

logger = get_logger(__name__)

# Bot API getFile orqali yuklab olish chegarasi.
BOT_API_DOWNLOAD_LIMIT = 20 * 1024 * 1024

ALLOWED_MIME: dict[MediaType, frozenset[str] | None] = {
    MediaType.PHOTO: frozenset({"image/jpeg", "image/png", "image/webp"}),
    MediaType.VIDEO: frozenset({"video/mp4", "video/quicktime", "video/webm"}),
    MediaType.ANIMATION: frozenset({"video/mp4", "image/gif"}),
    MediaType.AUDIO: frozenset(
        {
            "audio/mpeg",
            "audio/mp4",
            "audio/x-m4a",
            "audio/aac",
            "audio/ogg",
            "audio/wav",
            "audio/x-wav",
            "audio/flac",
        }
    ),
    MediaType.VOICE: frozenset({"audio/ogg", "audio/mpeg", "audio/x-opus+ogg"}),
    MediaType.DOCUMENT: None,  # har qanday hujjat, bajariladigan fayllardan tashqari
}
BLOCKED_DOCUMENT_EXTENSIONS = frozenset(
    {".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".ps1", ".sh", ".apk", ".jar", ".vbs"}
)
EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "application/pdf": ".pdf",
}
ALBUM_GROUPS: tuple[frozenset[MediaType], ...] = (
    frozenset({MediaType.PHOTO, MediaType.VIDEO}),
    frozenset({MediaType.DOCUMENT}),
    frozenset({MediaType.AUDIO}),
)
MAX_ALBUM = 10


class MediaMissingError(FileNotFoundError):
    """Bazada bor, lekin diskda topilmadi."""


class MediaInUseError(ValueError):
    """Media post shablonida ishlatilmoqda — o'chirib bo'lmaydi."""


@dataclass(frozen=True, slots=True)
class IncomingMedia:
    """Bot qabul qilgan fayl haqida (Telegram bergan) ma'lumot."""

    file_id: str
    media_type: MediaType
    mime_type: str
    size: int | None
    original_name: str | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None


def check_album(types: list[MediaType]) -> None:
    if len(types) > MAX_ALBUM:
        raise InputValidationError(f"Albomda ko'pi bilan {MAX_ALBUM} ta fayl bo'lishi mumkin")
    if len(types) <= 1:
        return
    kinds = set(types)
    if not any(kinds <= group for group in ALBUM_GROUPS):
        raise InputValidationError(
            "Albomga faqat rasm+video, faqat hujjatlar yoki faqat audio birga qo'shiladi. "
            "Ovozli xabar va GIF alohida yuboriladi."
        )


class MediaService:
    def __init__(self, database: Database, storage_dir: Path, max_size_bytes: int) -> None:
        self._database = database
        self._storage = storage_dir
        self.max_size = min(max_size_bytes, BOT_API_DOWNLOAD_LIMIT)

    def validate(self, incoming: IncomingMedia) -> None:
        if incoming.size is not None and incoming.size > self.max_size:
            limit_mb = self.max_size // (1024 * 1024)
            raise InputValidationError(f"Fayl juda katta: ko'pi bilan {limit_mb} MB")
        allowed = ALLOWED_MIME[incoming.media_type]
        mime = incoming.mime_type.lower()
        if allowed is not None and mime not in allowed:
            raise InputValidationError(f"Bu fayl turi qo'llab-quvvatlanmaydi: {mime}")
        if incoming.media_type is MediaType.DOCUMENT:
            suffix = Path(incoming.original_name or "").suffix.lower()
            if suffix in BLOCKED_DOCUMENT_EXTENSIONS:
                raise InputValidationError("Bajariladigan fayllar qabul qilinmaydi")

    def _extension(self, incoming: IncomingMedia) -> str:
        suffix = Path(incoming.original_name or "").suffix.lower()
        if suffix and len(suffix) <= 8 and suffix[1:].isalnum():
            return suffix
        return EXTENSIONS.get(incoming.mime_type.lower(), ".bin")

    async def store_from_bot(self, bot: Any, incoming: IncomingMedia) -> MediaFile:
        """Botdan faylni yuklab oladi, tekshiradi va saqlaydi (bir xil fayl qayta saqlanmaydi)."""
        self.validate(incoming)
        tmp_dir = safe_storage_path(self._storage, "tmp")
        tmp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = tmp_dir / f"{uuid.uuid4().hex}.part"
        try:
            await bot.download(incoming.file_id, destination=temporary)
            size = temporary.stat().st_size
            if size > self.max_size:
                raise InputValidationError("Fayl juda katta")
            # Katta faylni xeshlash event loop'ni to'xtatmasligi uchun alohida thread'da.
            digest = await asyncio.to_thread(sha256_file, temporary)
            async with self._database.session() as session:
                repo = MediaRepository(session)
                existing = await repo.get_by_sha(digest)
                if existing is not None:
                    target = self._absolute(existing.storage_path)
                    if not target.exists():
                        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        await asyncio.to_thread(shutil.move, temporary, target)
                    existing.is_missing = False
                    return existing
                relative = f"media/{digest[:2]}/{digest}{self._extension(incoming)}"
                target = self._absolute(relative)
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                await asyncio.to_thread(shutil.move, temporary, target)
                os.chmod(target, 0o600)
                return await repo.add(
                    MediaFile(
                        sha256=digest,
                        storage_path=relative,
                        original_name=incoming.original_name[:255]
                        if incoming.original_name
                        else None,
                        mime_type=incoming.mime_type[:127],
                        media_type=incoming.media_type,
                        size_bytes=size,
                        width=incoming.width,
                        height=incoming.height,
                        duration_seconds=incoming.duration,
                    )
                )
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()

    def _absolute(self, relative: str) -> Path:
        return safe_storage_path(self._storage, relative)

    async def path_for(self, media: MediaFile) -> Path:
        """Diskdagi yo'l; fayl yo'q bo'lsa bazada belgilab ``MediaMissingError``."""
        path = self._absolute(media.storage_path)
        if not path.is_file():
            async with self._database.session() as session:
                await MediaRepository(session).set_missing(media.id, True)
            raise MediaMissingError(media.storage_path)
        return path

    async def get(self, media_id: int) -> MediaFile | None:
        async with self._database.session() as session:
            return await MediaRepository(session).get(media_id)

    async def get_many(self, media_ids: list[int]) -> list[MediaFile]:
        async with self._database.session() as session:
            return await MediaRepository(session).get_many(media_ids)

    async def page(self, page: int, per_page: int = 8) -> tuple[list[MediaFile], int, int]:
        async with self._database.session() as session:
            repo = MediaRepository(session)
            _, total = await repo.page(1, 0)
            pages = max(1, -(-total // per_page))
            page = min(max(0, page), pages - 1)
            items, total = await repo.page(per_page, page * per_page)
        return items, page, pages

    async def usage_count(self, media_id: int) -> int:
        async with self._database.session() as session:
            return await MediaRepository(session).usage_count(media_id)

    async def delete(self, media_id: int) -> bool:
        async with self._database.session() as session:
            repo = MediaRepository(session)
            media = await repo.get(media_id)
            if media is None:
                return False
            if await repo.usage_count(media_id):
                raise MediaInUseError(media_id)
            relative = media.storage_path
            await repo.delete(media_id)
        with contextlib.suppress(FileNotFoundError):
            self._absolute(relative).unlink()
        return True

    def cleanup_temporary(self) -> int:
        """Ishga tushishda qolib ketgan vaqtinchalik fayllarni o'chiradi."""
        tmp_dir = self._storage / "tmp"
        removed = 0
        if tmp_dir.is_dir():
            for leftover in tmp_dir.glob("*.part"):
                with contextlib.suppress(FileNotFoundError):
                    leftover.unlink()
                    removed += 1
        return removed
