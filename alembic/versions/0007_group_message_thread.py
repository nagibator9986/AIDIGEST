"""add groups.message_thread_id

Stores the Telegram forum topic used for scheduled digest delivery. ``NULL``
keeps the previous behaviour: messages go to the main chat.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("message_thread_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("groups", "message_thread_id")
