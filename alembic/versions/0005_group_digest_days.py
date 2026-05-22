"""add groups.digest_days

Stores the ISO weekdays (1..7) on which a chat accepts scheduled digests.
Existing chats are backfilled to "every day".

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_all_days = sa.text("'[1,2,3,4,5,6,7]'::jsonb")


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column("digest_days", _json, nullable=False, server_default=_all_days),
    )


def downgrade() -> None:
    op.drop_column("groups", "digest_days")
