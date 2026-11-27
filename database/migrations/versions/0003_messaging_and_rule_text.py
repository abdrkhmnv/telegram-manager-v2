"""Xabar tarixi uchun qisqa matn va forward qoidalari uchun sarlavha/izoh matni.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE message_logs ADD COLUMN preview VARCHAR(100)",
    "ALTER TABLE forward_rules ADD COLUMN header_text TEXT",
    "ALTER TABLE forward_rules ADD COLUMN footer_text TEXT",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE forward_rules DROP COLUMN IF EXISTS footer_text")
    op.execute("ALTER TABLE forward_rules DROP COLUMN IF EXISTS header_text")
    op.execute("ALTER TABLE message_logs DROP COLUMN IF EXISTS preview")
