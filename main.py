"""Telegram Manager v2 — kirish nuqtasi.

Buyruqlar:
    python main.py run      — ilovani ishga tushirish (standart)
    python main.py check    — konfiguratsiya, PostgreSQL va migratsiyalarni tekshirish
                              (Docker healthcheck ham shundan foydalanadi)
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.bootstrap import (
    build_application,
    configure_logging,
    ensure_storage_dirs,
    run_application,
)
from app.config import (
    AppSettings,
    DatabaseSettings,
    format_settings_error,
    get_app_settings,
    get_database_settings,
)
from core.exceptions import AppError
from database.connection import Database
from database.migration_check import get_migration_status
from utils.logger import get_logger, redactor

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG_ERROR = 2

logger = get_logger("main")


def _load_settings() -> tuple[AppSettings, DatabaseSettings]:
    return get_app_settings(), get_database_settings()


async def _check(db_settings: DatabaseSettings) -> int:
    database = Database(db_settings)
    try:
        await database.wait_until_ready(attempts=1)
        status = await get_migration_status(database)
    except (AppError, SQLAlchemyError, OSError) as exc:
        print(f"XATO: {type(exc).__name__}: {redactor.redact(str(exc))}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        await database.dispose()
    print("PostgreSQL: OK")
    if not status.is_current:
        print(
            "Migratsiyalar: ESKIRGAN "
            f"(joriy: {sorted(status.current)}, kerak: {sorted(status.heads)}). "
            "Bajaring: alembic upgrade head",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    print(f"Migratsiyalar: OK ({', '.join(sorted(status.current))})")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="telegram-manager-v2")
    parser.add_argument("command", nargs="?", default="run", choices=("run", "check"))
    args = parser.parse_args(argv)

    try:
        app_settings, db_settings = _load_settings()
    except ValidationError as exc:
        print(format_settings_error(exc), file=sys.stderr)
        return EXIT_CONFIG_ERROR

    configure_logging(app_settings)

    if args.command == "check":
        return asyncio.run(_check(db_settings))

    ensure_storage_dirs(app_settings)
    application = build_application(app_settings, db_settings)
    try:
        asyncio.run(run_application(application))
    except AppError as exc:
        logger.error("Ilova ishga tushmadi: %s", exc)
        return EXIT_FAILURE
    except KeyboardInterrupt:
        pass
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
