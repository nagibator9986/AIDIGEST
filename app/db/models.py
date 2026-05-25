"""ORM models — the physical schema of the bot.

Three core entities:

* :class:`Group`      — every Telegram chat the bot was added to.
* :class:`NewsItem`   — the news pool, from RAW ingestion to POSTED.
* :class:`DeliveryLog` — audit trail of every digest sent to every chat.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.config import ALL_DIGEST_WEEKDAYS
from app.db.base import Base
from app.domain.enums import DeliveryStatus, NewsCategory, NewsStatus

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite in tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class TimestampMixin:
    """Adds DB-managed ``created_at`` / ``updated_at`` columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Group(TimestampMixin, Base):
    """A Telegram chat (group/supergroup/channel) subscribed to the digest."""

    __tablename__ = "groups"

    # Telegram chat id — negative for groups; fits in BigInteger.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    chat_type: Mapped[str] = mapped_column(String(32), default="group")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Telegram forum topic for digest delivery. ``None`` means the main chat.
    message_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Per-chat delivery schedule: a list of "HH:MM" slots interpreted in
    # `timezone`. One digest is delivered per slot per day.
    digest_times: Mapped[list[str]] = mapped_column(JSONType, default=lambda: ["09:00"])
    # ISO weekdays 1..7 (Mon..Sun) on which the scheduled digest is allowed.
    digest_days: Mapped[list[int]] = mapped_column(
        JSONType, default=lambda: list(ALL_DIGEST_WEEKDAYS)
    )
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    # User-controlled pause (distinct from `is_active`, which tracks whether
    # the bot is present in the chat).
    digest_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Local date the `sent_slots_today` list refers to.
    last_digest_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Slots ("HH:MM") already delivered on `last_digest_on` — the double-send
    # guard for multi-slot schedules.
    sent_slots_today: Mapped[list[str]] = mapped_column(JSONType, default=list)

    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    deliveries: Mapped[list[DeliveryLog]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Group id={self.id} title={self.title!r} active={self.is_active}>"


class NewsItem(TimestampMixin, Base):
    """One unit in the news pool, tracked through the whole pipeline."""

    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("normalized_url", name="uq_news_normalized_url"),
        Index("ix_news_status_score", "status", "score"),
        Index("ix_news_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, default="")

    # Provenance.
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # Text, not a bounded VARCHAR: RSS feeds often use long URIs as entry ids.
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Preview image (og:image) for the item — populated lazily at digest time.
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # URLs of merged duplicates from other sources.
    extra_sources: Mapped[list[str]] = mapped_column(JSONType, default=list)

    # Pipeline state.
    status: Mapped[NewsStatus] = mapped_column(
        String(20), default=NewsStatus.RAW, nullable=False, index=True
    )

    # Gemini verdict (populated by the scoring stage).
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[NewsCategory | None] = mapped_column(String(32), nullable=True)
    summary_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    utility_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Short factual bullet points produced by the scorer.
    key_points: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)
    is_hype: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Telegram user id of the moderator who approved/rejected, if any.
    moderated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NewsItem {self.status} score={self.score} {self.title[:40]!r}>"


class DeliveryLog(Base):
    """Audit record: one digest delivered (or not) to one chat at one slot."""

    __tablename__ = "delivery_log"
    __table_args__ = (Index("ix_delivery_group_date", "group_id", "digest_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Schedule slot ("HH:MM") this delivery was for; NULL for manual sends.
    slot: Mapped[str | None] = mapped_column(String(5), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[DeliveryStatus] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    group: Mapped[Group] = relationship(back_populates="deliveries")
