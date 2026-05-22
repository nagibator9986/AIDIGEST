"""news item key points

Adds ``news_items.key_points`` — the short factual bullet points produced by
the Gemini scorer alongside the summary.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("news_items", sa.Column("key_points", _json, nullable=True))


def downgrade() -> None:
    op.drop_column("news_items", "key_points")
