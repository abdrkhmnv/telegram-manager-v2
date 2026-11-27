"""Handlerlarga dispatcher ``workflow_data`` orqali uzatiladigan servislar to'plami."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from services.autopost_service import AutopostService
    from services.chat_service import ChatService
    from services.forwarding_service import ForwardRuleService
    from services.media_service import MediaService
    from services.message_service import MessageService
    from services.statistics_service import StatisticsService
    from services.status_service import StatusService


@dataclass(slots=True)
class Services:
    status: StatusService
    chats: ChatService
    messages: MessageService
    media: MediaService
    rules: ForwardRuleService
    autopost: AutopostService
    stats: StatisticsService
    timezone: ZoneInfo
