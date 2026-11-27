"""Ma'lumotlar bazasi sxemasi oxirgi Alembic migratsiyasida ekanini tekshirish."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from database.connection import Database

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"


@dataclass(frozen=True)
class MigrationStatus:
    current: frozenset[str]
    heads: frozenset[str]

    @property
    def is_current(self) -> bool:
        return bool(self.heads) and self.current == self.heads


def get_head_revisions() -> frozenset[str]:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


async def get_current_revisions(database: Database) -> frozenset[str]:
    async with database.engine.connect() as connection:
        table = await connection.scalar(text("SELECT to_regclass('alembic_version')"))
        if table is None:
            return frozenset()
        rows = await connection.scalars(text("SELECT version_num FROM alembic_version"))
        return frozenset(rows.all())


async def get_migration_status(database: Database) -> MigrationStatus:
    return MigrationStatus(
        current=await get_current_revisions(database), heads=get_head_revisions()
    )
