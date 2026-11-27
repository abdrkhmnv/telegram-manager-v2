"""Servislardagi sof funksiyalar (bazasiz)."""

from __future__ import annotations

from datetime import UTC, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("telethon")

from telethon.errors import ChatWriteForbiddenError, FloodWaitError

from core.telegram_errors import describe_error
from database.models import AutopostKind, ChatType, ForwardMode, MediaType, Recurrence
from services.chat_service import snapshot_from_entity
from services.forwarding_service import (
    RuleSnapshot,
    compose,
    content_hash,
    media_kind,
    rule_matches,
)
from services.media_service import check_album
from services.message_service import plain_preview
from services.scheduling_service import next_slot
from tests.helpers.fakes import entity, tg_message
from utils.validators import InputValidationError

TZ = ZoneInfo("Asia/Tashkent")


def rule(**kwargs: object) -> RuleSnapshot:
    base: dict[str, object] = {
        "id": 1,
        "name": "r",
        "mode": ForwardMode.COPY,
        "sources": frozenset({-1}),
        "destinations": (-2,),
    }
    base.update(kwargs)
    return RuleSnapshot(**base)  # type: ignore[arg-type]


class TestSnapshots:
    def test_types_and_marked_ids(self) -> None:
        user = snapshot_from_entity(entity("User", 5, first_name="Ali", last_name="V"))
        assert user is not None and (user.telegram_id, user.chat_type, user.title) == (
            5,
            ChatType.PRIVATE,
            "Ali V",
        )
        group = snapshot_from_entity(entity("Chat", 7, title="G", participants_count=3))
        assert group is not None and (group.telegram_id, group.members_count) == (-7, 3)
        channel = snapshot_from_entity(entity("Channel", 9, title="C", megagroup=False))
        assert channel is not None and channel.telegram_id == -1000000000009
        assert channel.chat_type is ChatType.CHANNEL
        mega = snapshot_from_entity(entity("Channel", 9, title="C", megagroup=True))
        assert mega is not None and mega.chat_type is ChatType.SUPERGROUP

    @pytest.mark.parametrize(
        "obj",
        [
            entity("User", 1, deleted=True),
            entity("Channel", 2, left=True),
            entity("Chat", 3, deactivated=True),
            entity("ChannelForbidden", 4),
        ],
    )
    def test_unusable_entities_are_skipped(self, obj: object) -> None:
        assert snapshot_from_entity(obj) is None


class TestForwardHelpers:
    def test_rule_matching(self) -> None:
        assert rule_matches(rule(), "har qanday", {"text"})
        keyworded = rule(include=("aksiya",), exclude=("reklama",))
        assert rule_matches(keyworded, "Katta AKSIYA", {"text"})
        assert not rule_matches(keyworded, "oddiy", {"text"})
        assert not rule_matches(keyworded, "aksiya reklama", {"text"})
        photos_only = rule(media_types=frozenset({"photo"}))
        assert rule_matches(photos_only, "", {"photo"})
        assert not rule_matches(photos_only, "", {"text"})

    def test_media_kind(self) -> None:
        assert media_kind(tg_message(1, "x")) == "text"
        assert media_kind(tg_message(1, photo_id=5)) == "photo"
        assert media_kind(tg_message(1, document_id=5)) == "document"
        voice = tg_message(1, document_id=5)
        voice.voice = object()
        assert media_kind(voice) == "voice"
        poll = tg_message(1)
        poll.media = SimpleNamespace()
        assert media_kind(poll) == "other"

    def test_content_hash_depends_on_text_and_media(self) -> None:
        a = content_hash([tg_message(1, "x", photo_id=1)])
        assert a == content_hash([tg_message(2, "x", photo_id=1)])
        assert a != content_hash([tg_message(1, "x", photo_id=2)])
        assert a != content_hash([tg_message(1, "y", photo_id=1)])

    def test_compose(self) -> None:
        assert compose("H", "B", "F") == "H\n\nB\n\nF"
        assert compose(None, "B", " ") == "B"


class TestMediaAndText:
    def test_album_rules(self) -> None:
        check_album([MediaType.PHOTO, MediaType.VIDEO])
        check_album([MediaType.DOCUMENT] * 3)
        check_album([MediaType.VOICE])
        for bad in (
            [MediaType.PHOTO, MediaType.DOCUMENT],
            [MediaType.VOICE, MediaType.VOICE],
            [MediaType.PHOTO] * 11,
        ):
            with pytest.raises(InputValidationError):
                check_album(bad)

    def test_plain_preview(self) -> None:
        assert plain_preview("<b>Salom</b> &amp; xayr") == "Salom & xayr"
        assert plain_preview(None) == "—"

    def test_describe_error(self) -> None:
        assert (
            describe_error(ChatWriteForbiddenError(request=None)) == "Bu chatga yozish huquqi yo'q"
        )
        assert "30 soniya" in describe_error(FloodWaitError(request=None, capture=30))
        assert "Chat topilmadi" in describe_error(ValueError("Could not find the input entity"))
        assert describe_error(ConnectionError()) == "Tarmoq xatosi, keyinroq qayta urinib ko'ring"


class TestNextSlot:
    AFTER = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)  # 17:00 Toshkent, juma

    def task(self, **kwargs: object) -> SimpleNamespace:
        base: dict[str, object] = {
            "kind": AutopostKind.SCHEDULED,
            "recurrence": Recurrence.DAILY,
            "time_of_day": time(9, 0),
            "weekdays_mask": None,
            "min_interval_seconds": None,
            "max_interval_seconds": None,
            "active_from": None,
            "active_to": None,
        }
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_daily_weekly_once(self) -> None:
        assert next_slot(self.task(), self.AFTER, TZ) == datetime(2026, 11, 28, 4, 0, tzinfo=UTC)  # type: ignore[arg-type]
        weekly = self.task(recurrence=Recurrence.WEEKLY, weekdays_mask=1)
        assert next_slot(weekly, self.AFTER, TZ) == datetime(2026, 11, 30, 4, 0, tzinfo=UTC)  # type: ignore[arg-type]
        assert next_slot(self.task(recurrence=Recurrence.ONCE), self.AFTER, TZ) is None  # type: ignore[arg-type]

    def test_random_within_bounds(self) -> None:
        task = self.task(
            kind=AutopostKind.RANDOM,
            recurrence=None,
            min_interval_seconds=600,
            max_interval_seconds=900,
        )
        slot = next_slot(task, self.AFTER, TZ)  # type: ignore[arg-type]
        assert slot is not None
        assert 600 <= (slot - self.AFTER).total_seconds() <= 900
