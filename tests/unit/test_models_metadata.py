"""Model metadata va migratsiya mosligining bazasiz tekshiruvi.

To'liq tekshiruv (ustun turlari, indekslar) CI'da ``alembic check`` orqali
haqiqiy PostgreSQL'da bajariladi. Bu testlar esa tez va bazasiz ishlaydi.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

sa = pytest.importorskip("sqlalchemy")

from sqlalchemy import CheckConstraint, Enum  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateTable  # noqa: E402

import database.models as models  # noqa: E402
from database.base import Base  # noqa: E402

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "database"
    / "migrations"
    / "versions"
    / "0001_initial_schema.py"
)

REQUIRED_TABLES = {
    "settings",
    "chats",
    "chat_categories",
    "forward_rules",
    "forward_logs",
    "autopost_tasks",
    "scheduled_posts",
    "post_templates",
    "media_files",
    "message_logs",
    "task_logs",
    "activity_logs",
}


def _migration_sql() -> str:
    """Migratsiyani soxta ``alembic.op`` bilan yuklab, SQL matnini qaytaradi."""
    statements: list[str] = []
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = types.SimpleNamespace(execute=statements.append)  # type: ignore[attr-defined]
    saved = sys.modules.get("alembic")
    sys.modules["alembic"] = fake_alembic
    try:
        spec = importlib.util.spec_from_file_location("_mig_0001", MIGRATION)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.upgrade()
    finally:
        if saved is not None:
            sys.modules["alembic"] = saved
        else:
            sys.modules.pop("alembic", None)
    return "\n".join(statements)


def test_required_tables_registered() -> None:
    assert set(Base.metadata.tables) >= REQUIRED_TABLES


def test_every_model_table_is_created_by_migration() -> None:
    sql = _migration_sql()
    created = set(re.findall(r"CREATE TABLE (\w+)", sql))
    assert created == set(Base.metadata.tables)


def test_index_and_constraint_names_match_migration() -> None:
    sql = _migration_sql()
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            assert re.search(rf"CREATE INDEX {index.name}\s+ON {table.name} ", sql), index.name
        for constraint in table.constraints:
            name = str(constraint.name)
            kind = "CHECK" if isinstance(constraint, CheckConstraint) else r"\w+"
            assert re.search(rf"CONSTRAINT {name}\s+{kind}", sql), (table.name, name)


def test_enum_checks_list_same_values_as_python_enums() -> None:
    sql = _migration_sql()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, Enum):
                expected = ", ".join(f"'{v}'" for v in column.type.enums)
                assert f"CHECK ({column.name} IN ({expected}))" in sql, (table.name, column.name)


def test_enum_stores_values_not_names() -> None:
    column = models.Chat.__table__.c.chat_type
    assert column.type.enums == ["private", "group", "supergroup", "channel"]
    assert column.type.length == 32


def test_models_compile_for_postgresql() -> None:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert table.name in ddl


def test_timestamps_are_timezone_aware() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, sa.DateTime):
                assert column.type.timezone, f"{table.name}.{column.name}"
