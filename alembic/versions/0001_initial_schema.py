"""initial schema: groups, news_items, delivery_log

Revision ID: 0001
Revises:
Create Date: 2026-05-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSONB on PostgreSQL, JSON elsewhere — keeps the migration portable.
_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "chat_type", sa.String(length=32), nullable=False, server_default="group"
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "digest_time", sa.String(length=5), nullable=False, server_default="09:00"
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="Europe/Moscow",
        ),
        sa.Column("last_digest_on", sa.Date(), nullable=True),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_groups_is_active", "groups", ["is_active"])

    op.create_table(
        "news_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_sources", _json, nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="raw"
        ),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("summary_ru", sa.Text(), nullable=True),
        sa.Column("utility_ru", sa.Text(), nullable=True),
        sa.Column("is_hype", sa.Boolean(), nullable=True),
        sa.Column("score_reasoning", sa.Text(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderated_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_url", name="uq_news_normalized_url"),
    )
    op.create_index("ix_news_items_status", "news_items", ["status"])
    op.create_index("ix_news_status_score", "news_items", ["status", "score"])
    op.create_index("ix_news_created_at", "news_items", ["created_at"])

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

    op.create_table(
        "delivery_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_delivery_group_date", "delivery_log", ["group_id", "digest_date"]
    )


def downgrade() -> None:
    op.drop_table("delivery_log")
    op.drop_table("digests")
    op.drop_table("news_items")
    op.drop_index("ix_groups_is_active", table_name="groups")
    op.drop_table("groups")
