"""add news_items.image_url

Stores a preview image (og:image) for a news item, populated lazily when the
item is selected for a digest so deliveries can be sent as photos.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("news_items", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("news_items", "image_url")
