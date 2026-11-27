"""Barcha modellar shu yerda import qilinadi — Alembic metadata'ni to'liq ko'rishi uchun."""

from database.models.autopost import (
    AutopostQueueItem,
    AutopostTask,
    ScheduledPost,
    autopost_task_destinations,
)
from database.models.bot_state import BotState
from database.models.chats import Chat, ChatCategory, chat_category_links
from database.models.enums import (
    AutopostKind,
    ChatType,
    DeliveryStatus,
    ForwardMode,
    MediaType,
    MessageOperation,
    OperationSource,
    PostStatus,
    Recurrence,
    RuleStatus,
    RunStatus,
    TaskStatus,
)
from database.models.forwarding import (
    ForwardLog,
    ForwardRule,
    forward_rule_destinations,
    forward_rule_sources,
)
from database.models.logs import ActivityLog, MessageLog, TaskLog
from database.models.media import MediaFile, PostTemplate, PostTemplateMedia
from database.models.settings import Setting

__all__ = [
    "ActivityLog",
    "AutopostKind",
    "AutopostQueueItem",
    "AutopostTask",
    "BotState",
    "Chat",
    "ChatCategory",
    "ChatType",
    "DeliveryStatus",
    "ForwardLog",
    "ForwardMode",
    "ForwardRule",
    "MediaFile",
    "MediaType",
    "MessageLog",
    "MessageOperation",
    "OperationSource",
    "PostStatus",
    "PostTemplate",
    "PostTemplateMedia",
    "Recurrence",
    "RuleStatus",
    "RunStatus",
    "ScheduledPost",
    "Setting",
    "TaskLog",
    "TaskStatus",
    "autopost_task_destinations",
    "chat_category_links",
    "forward_rule_destinations",
    "forward_rule_sources",
]
