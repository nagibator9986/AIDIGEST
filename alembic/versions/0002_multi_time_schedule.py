"""multi-time delivery schedule

Replaces the single per-chat ``digest_time`` with a list of delivery slots
(``digest_times``), adds a user-controlled pause and per-slot send tracking,
records the slot on each delivery, and drops the now-unused daily digest cache.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # groups: single digest_time -> list digest_times
    op.add_column("groups", sa.Column("digest_times", _json, nullable=True))
    op.execute(
        "UPDATE groups SET digest_times = json_build_array(digest_time)"
    )
    op.alter_column("groups", "digest_times", nullable=False)
    op.add_column(
        "groups",
        sa.Column(
            "digest_paused", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "groups",
        sa.Column(
            "sent_slots_today",
            _json,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.drop_column("groups", "digest_time")

    # delivery_log: record which schedule slot a delivery was for
    op.add_column(
        "delivery_log", sa.Column("slot", sa.String(length=5), nullable=True)
    )

    # the per-day digest cache is no longer used (digests are built on demand)
    op.drop_table("digests")


def downgrade() -> None:
    op.create_table(
        "digests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("item_ids", _json, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("digest_date", name="uq_digest_date"),
    )

    op.drop_column("delivery_log", "slot")

    op.add_column(
        "groups",
        sa.Column("digest_time", sa.String(length=5), nullable=False,
                  server_default="09:00"),
    )
    op.execute("UPDATE groups SET digest_time = digest_times->>0")
    op.drop_column("groups", "sent_slots_today")
    op.drop_column("groups", "digest_paused")
    op.drop_column("groups", "digest_times")
