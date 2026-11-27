"""Asinxron repozitoriylar.

Repozitoriylar tranzaksiyani o'zi commit qilmaydi: chaqiruvchi
``Database.session()`` bloki orqali bitta unit of work boshqaradi.
Barcha so'rovlar ORM/parametrlangan — SQL injection imkoni yo'q.
"""

from database.repositories.activity import ActivityLogRepository
from database.repositories.autopost import AutopostTaskRepository, ScheduledPostRepository
from database.repositories.chats import ChatRepository, ChatSnapshot
from database.repositories.forwarding import ForwardLogRepository
from database.repositories.settings import SettingsRepository

__all__ = [
    "ActivityLogRepository",
    "AutopostTaskRepository",
    "ChatRepository",
    "ChatSnapshot",
    "ForwardLogRepository",
    "ScheduledPostRepository",
    "SettingsRepository",
]
