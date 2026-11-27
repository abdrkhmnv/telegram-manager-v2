"""Ilova darajasidagi istisnolar."""

from __future__ import annotations


class AppError(Exception):
    """Barcha ilova xatolarining asosi."""


class ConfigurationError(AppError):
    """Konfiguratsiya noto'g'ri yoki to'liq emas."""


class StartupError(AppError):
    """Komponentni ishga tushirib bo'lmadi."""


class DatabaseUnavailableError(StartupError):
    """PostgreSQL bilan ulanish o'rnatilmadi."""


class MigrationOutOfDateError(StartupError):
    """Ma'lumotlar bazasi sxemasi oxirgi migratsiyada emas."""
