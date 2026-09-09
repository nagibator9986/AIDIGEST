"""move every chat onto the twice-weekly morning schedule

The product schedule is now exactly two deliveries per week: Monday morning and
Friday morning. Existing chats carry whatever schedule they were given under the
old "every day" default, so they are migrated onto the new one.

Chats that had customised their schedule are migrated too — the twice-weekly
cadence is a product decision, not a per-chat preference, and any chat can still
change it afterwards with /digest_time and /digest_days.

If the migration lands *on* a delivery day, that day's slot is marked consumed:
the same rule the app applies whenever a schedule changes, so a deploy never
triggers a surprise digest within the minute.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MON_FRI = sa.text("'[1,5]'::jsonb")
_ALL_DAYS = sa.text("'[1,2,3,4,5,6,7]'::jsonb")

_MIGRATE = sa.text(
    """
    UPDATE groups SET
        digest_days = '[1,5]'::jsonb,
        digest_times = '["09:00"]'::jsonb,
        last_digest_on = CASE
            WHEN EXTRACT(ISODOW FROM CURRENT_DATE) IN (1, 5) THEN CURRENT_DATE
            ELSE NULL
        END,
        sent_slots_today = CASE
            WHEN EXTRACT(ISODOW FROM CURRENT_DATE) IN (1, 5) THEN '["09:00"]'::jsonb
            ELSE '[]'::jsonb
        END
    """
)


def upgrade() -> None:
    # New chats get their schedule from DIGEST_DAYS/DIGEST_TIME, but the column
    # default is kept in step so a row inserted outside the app is sane too.
    op.alter_column("groups", "digest_days", server_default=_MON_FRI)
    op.execute(_MIGRATE)


def downgrade() -> None:
    op.alter_column("groups", "digest_days", server_default=_ALL_DAYS)
    op.execute(sa.text("UPDATE groups SET digest_days = '[1,2,3,4,5,6,7]'::jsonb"))
