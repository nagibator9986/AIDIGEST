"""widen news_items.external_id to TEXT

RSS feeds frequently use long URIs as entry ids, which overflow the original
VARCHAR(128). The column is non-indexed provenance metadata, so TEXT is fine.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "news_items",
        "external_id",
        type_=sa.Text(),
        existing_type=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "news_items",
        "external_id",
        type_=sa.String(length=128),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
