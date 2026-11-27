"""Model enumlari. Bazada ``.value`` (kichik harfli satr) saqlanadi."""

from __future__ import annotations

from enum import StrEnum


class ChatType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class ForwardMode(StrEnum):
    NATIVE = "native"
    COPY = "copy"


class RuleStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class AutopostKind(StrEnum):
    SCHEDULED = "scheduled"
    RANDOM = "random"


class TaskStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Recurrence(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class PostStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaType(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"
    ANIMATION = "animation"
    DOCUMENT = "document"
    AUDIO = "audio"
    VOICE = "voice"


class MessageOperation(StrEnum):
    SEND = "send"
    EDIT = "edit"
    DELETE = "delete"


class OperationSource(StrEnum):
    MANUAL = "manual"
    FORWARD = "forward"
    AUTOPOST = "autopost"
    RANDOM_POST = "random_post"


class RunStatus(StrEnum):
    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
