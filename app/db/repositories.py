"""Repositories — the only place that knows how data is queried.

Every function takes an :class:`AsyncSession` and never commits; transaction
boundaries belong to the caller (``session_scope`` or the bot middleware).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select, update

from app.config import ALL_DIGEST_WEEKDAYS, normalize_weekdays, parse_hhmm
from app.db.base import AsyncSession
from app.db.models import DeliveryLog, Group, NewsItem
from app.domain.enums import DeliveryStatus, NewsStatus
from app.domain.schemas import GeminiVerdict, RawItem
from app.utils.timeutil import now_in, utcnow

# ── Groups ─────────────────────────────────────────────────────────────────


def _passed_slots(
    times: list[str], tz: str, days: list[int] | None = None
) -> tuple[date, list[str]]:
    """Return ``(local_date, slots_already_passed_today)`` for *tz*.

    A chat registered (or re-activated) after some of its slots have already
    passed today must not get an unexpected digest within the minute — those
    slots are pre-marked as already delivered.
    """
    local = now_in(tz)
    allowed_days = set(days or ALL_DIGEST_WEEKDAYS)
    if local.isoweekday() not in allowed_days:
        return local.date(), []
    passed: list[str] = []
    for slot in times:
        try:
            if local.time() >= parse_hhmm(slot):
                passed.append(slot)
        except ValueError:  # pragma: no cover
            continue
    return local.date(), passed


def _resync_schedule_state(group: Group) -> None:
    """Recompute today's passed slots after a schedule-setting change.

    This intentionally treats a changed schedule as a *new* schedule: slots
    that are already in the past for the chat's current local day are marked as
    consumed immediately, so editing settings never triggers surprise catch-up
    sends for earlier times. Future slots on the same day remain deliverable.
    """
    if not group.digest_days:
        group.digest_days = list(ALL_DIGEST_WEEKDAYS)
    today, passed = _passed_slots(group.digest_times, group.timezone, group.digest_days)
    group.last_digest_on = today if passed else None
    group.sent_slots_today = passed


async def upsert_group(
    session: AsyncSession,
    *,
    chat_id: int,
    title: str,
    chat_type: str,
    added_by: int | None,
    default_time: str,
    default_tz: str,
) -> tuple[Group, bool]:
    """Insert a group or re-activate an existing one. Returns ``(group, created)``."""
    group = await session.get(Group, chat_id)

    if group is None:
        times = [default_time]
        digest_days = list(ALL_DIGEST_WEEKDAYS)
        today, passed = _passed_slots(times, default_tz, digest_days)
        group = Group(
            id=chat_id,
            title=title,
            chat_type=chat_type,
            added_by=added_by,
            digest_times=times,
            digest_days=digest_days,
            timezone=default_tz,
            # Slots already past today are pre-marked as delivered.
            last_digest_on=today if passed else None,
            sent_slots_today=passed,
        )
        session.add(group)
        return group, True

    group.title = title or group.title
    group.chat_type = chat_type or group.chat_type
    group.is_active = True
    if not group.digest_days:
        group.digest_days = list(ALL_DIGEST_WEEKDAYS)
    # On re-activation for a new day, pre-mark slots that have already passed.
    today, passed = _passed_slots(group.digest_times, group.timezone, group.digest_days)
    if group.last_digest_on != today:
        group.last_digest_on = today if passed else None
        group.sent_slots_today = passed
    return group, False


async def deactivate_group(session: AsyncSession, chat_id: int) -> None:
    """Mark a group inactive (bot removed / chat unreachable)."""
    await session.execute(update(Group).where(Group.id == chat_id).values(is_active=False))


async def get_group(session: AsyncSession, chat_id: int) -> Group | None:
    return await session.get(Group, chat_id)


async def list_active_groups(session: AsyncSession) -> list[Group]:
    result = await session.execute(
        select(Group).where(Group.is_active.is_(True)).order_by(Group.id)
    )
    return list(result.scalars())


async def set_digest_times(session: AsyncSession, chat_id: int, times: list[str]) -> bool:
    """Replace a chat's delivery schedule. Returns False if the chat is unknown."""
    group = await session.get(Group, chat_id)
    if group is None:
        return False
    group.digest_times = times
    _resync_schedule_state(group)
    return True


async def set_digest_days(session: AsyncSession, chat_id: int, days: list[int]) -> bool:
    """Replace a chat's allowed delivery weekdays. Returns False if unknown."""
    group = await session.get(Group, chat_id)
    if group is None:
        return False
    group.digest_days = normalize_weekdays(days)
    _resync_schedule_state(group)
    return True


async def set_timezone(session: AsyncSession, chat_id: int, tz: str) -> bool:
    """Update a chat's timezone. Returns False if the chat is unknown."""
    group = await session.get(Group, chat_id)
    if group is None:
        return False
    group.timezone = tz
    _resync_schedule_state(group)
    return True


async def set_paused(session: AsyncSession, chat_id: int, paused: bool) -> bool:
    """Pause or resume digests for a chat. Returns False if the chat is unknown."""
    group = await session.get(Group, chat_id)
    if group is None:
        return False
    group.digest_paused = paused
    if not paused:
        _resync_schedule_state(group)
    return True


async def set_message_thread(
    session: AsyncSession, chat_id: int, message_thread_id: int | None
) -> bool:
    """Route digest messages to a Telegram forum topic. Returns False if unknown."""
    group = await session.get(Group, chat_id)
    if group is None:
        return False
    group.message_thread_id = message_thread_id
    return True


async def mark_slot_sent(session: AsyncSession, chat_id: int, on_date: date, slot: str) -> None:
    """Record that *slot* was delivered to *chat_id* on *on_date*.

    Resets the per-day slot list when the local date rolls over.
    """
    group = await session.get(Group, chat_id)
    if group is None:
        return
    if group.last_digest_on != on_date:
        group.last_digest_on = on_date
        group.sent_slots_today = [slot]
    elif slot not in group.sent_slots_today:
        group.sent_slots_today = [*group.sent_slots_today, slot]


# ── News pool ──────────────────────────────────────────────────────────────


async def get_existing_normalized_urls(
    session: AsyncSession, normalized_urls: list[str]
) -> set[str]:
    """Return the subset of *normalized_urls* already present in the pool."""
    if not normalized_urls:
        return set()
    result = await session.execute(
        select(NewsItem.normalized_url).where(NewsItem.normalized_url.in_(normalized_urls))
    )
    return set(result.scalars())


async def insert_raw_item(session: AsyncSession, item: RawItem) -> NewsItem:
    """Persist a freshly collected item with ``RAW`` status."""
    news = NewsItem(
        title=item.title,
        source_url=item.url,
        normalized_url=item.normalized_url,
        raw_content=item.raw_content,
        source=item.source,
        external_id=item.external_id,
        points=item.points,
        published_at=item.published_at,
        status=NewsStatus.RAW,
        extra_sources=[],
    )
    session.add(news)
    return news


async def recent_titles(session: AsyncSession, *, since: datetime) -> list[tuple[uuid.UUID, str]]:
    """Return ``(id, title)`` of items created since *since* — for fuzzy dedup."""
    result = await session.execute(
        select(NewsItem.id, NewsItem.title).where(NewsItem.created_at >= since)
    )
    return [(row[0], row[1]) for row in result.all()]


async def add_extra_source(session: AsyncSession, item_id: uuid.UUID, url: str) -> None:
    """Attach a duplicate's URL to the canonical item it was merged into."""
    item = await session.get(NewsItem, item_id)
    if item is None:
        return
    sources = list(item.extra_sources or [])
    if url not in sources:
        sources.append(url)
        item.extra_sources = sources


# Source priority for the scoring queue: vendor blogs and research first,
# trending tools last. Lower number = scored sooner within the budget.
_SOURCE_RANK = case(
    {
        "rss": 0,
        "technews": 1,
        "huggingface": 2,
        "hackernews": 3,
        "producthunt": 4,
        "github": 5,
    },
    value=NewsItem.source,
    else_=9,
)


# Round-robin order across sources, so a limited scoring budget spans every
# source instead of being eaten by whichever source collected the most items.
_SOURCE_ORDER = ("rss", "technews", "huggingface", "hackernews", "producthunt", "github")


async def list_unscored(session: AsyncSession, limit: int = 100) -> list[NewsItem]:
    """Return RAW items to score — diversified across sources, best first.

    Within each source items are ordered by popularity then age; sources are
    then interleaved round-robin. This guarantees a small Gemini budget is
    spread over vendor blogs, research, discussions *and* trending tools,
    rather than being consumed entirely by the largest single source.
    """
    result = await session.execute(
        select(NewsItem)
        .where(NewsItem.status == NewsStatus.RAW)
        .order_by(
            _SOURCE_RANK,
            NewsItem.points.desc().nullslast(),
            NewsItem.created_at,
        )
        .limit(limit * 6)  # bounded pool to interleave
    )
    buckets: dict[str, list[NewsItem]] = {}
    for item in result.scalars():
        buckets.setdefault(item.source, []).append(item)

    # Sources in priority order, with any unknown source appended last.
    sources = [s for s in _SOURCE_ORDER if s in buckets]
    sources += [s for s in buckets if s not in _SOURCE_ORDER]

    picked: list[NewsItem] = []
    cursors = dict.fromkeys(sources, 0)
    while len(picked) < limit and any(cursors[s] < len(buckets[s]) for s in sources):
        for source in sources:
            idx = cursors[source]
            if idx < len(buckets[source]):
                picked.append(buckets[source][idx])
                cursors[source] = idx + 1
                if len(picked) >= limit:
                    break
    return picked


async def apply_verdict(
    session: AsyncSession,
    item: NewsItem,
    verdict: GeminiVerdict,
    *,
    status: NewsStatus,
) -> None:
    """Write a Gemini verdict onto an item and advance its status."""
    item.score = verdict.score
    item.category = verdict.category
    item.summary_ru = verdict.summary_ru
    item.utility_ru = verdict.utility_ru
    item.key_points = verdict.key_points_ru
    item.is_hype = verdict.is_hype
    item.score_reasoning = verdict.reasoning
    item.scored_at = utcnow()
    item.status = status


async def mark_failed(session: AsyncSession, item: NewsItem) -> None:
    item.status = NewsStatus.FAILED
    item.scored_at = utcnow()


async def get_news(session: AsyncSession, item_id: uuid.UUID) -> NewsItem | None:
    return await session.get(NewsItem, item_id)


async def set_status(
    session: AsyncSession,
    item_id: uuid.UUID,
    status: NewsStatus,
    *,
    moderated_by: int | None = None,
) -> NewsItem | None:
    item = await session.get(NewsItem, item_id)
    if item is None:
        return None
    item.status = status
    if moderated_by is not None:
        item.moderated_by = moderated_by
    return item


async def list_breaking_news(
    session: AsyncSession, *, item_ids: list[uuid.UUID] | None = None
) -> list[NewsItem]:
    """Urgent items that must bypass the group schedule."""
    stmt = (
        select(NewsItem)
        .where(NewsItem.status == NewsStatus.BREAKING)
        .order_by(
            NewsItem.score.desc(),
            NewsItem.scored_at.desc().nullslast(),
            NewsItem.created_at.desc(),
        )
    )
    if item_ids is not None:
        if not item_ids:
            return []
        stmt = stmt.where(NewsItem.id.in_(item_ids))
    result = await session.execute(stmt)
    return list(result.scalars())


async def select_digest_items(
    session: AsyncSession, *, lookback_days: int, threshold: int, limit: int
) -> list[NewsItem]:
    """Best approved, not-yet-posted items for the next digest, top first.

    Considers everything ingested in the last *lookback_days* days — so the
    digest surfaces the most significant and popular AI news of the period,
    not just the last 24 hours. Ranked by Gemini significance, then by source
    popularity (points/upvotes).
    """
    since = utcnow() - timedelta(days=lookback_days)
    result = await session.execute(
        select(NewsItem)
        .where(
            NewsItem.status == NewsStatus.APPROVED,
            NewsItem.score >= threshold,
            NewsItem.created_at >= since,
        )
        .order_by(
            NewsItem.score.desc(),
            NewsItem.points.desc().nullslast(),
            NewsItem.created_at.desc(),
        )
        .limit(limit)
    )
    return list(result.scalars())


async def mark_posted(session: AsyncSession, item_ids: list[uuid.UUID]) -> None:
    if not item_ids:
        return
    await session.execute(
        update(NewsItem)
        .where(NewsItem.id.in_(item_ids))
        .values(status=NewsStatus.POSTED, posted_at=utcnow())
    )


# ── Delivery log ───────────────────────────────────────────────────────────


async def log_delivery(
    session: AsyncSession,
    *,
    group_id: int,
    digest_date: date,
    item_count: int,
    status: DeliveryStatus,
    slot: str | None = None,
    error: str | None = None,
) -> None:
    session.add(
        DeliveryLog(
            group_id=group_id,
            digest_date=digest_date,
            slot=slot,
            item_count=item_count,
            status=status,
            error=error,
        )
    )


# ── Statistics ─────────────────────────────────────────────────────────────


async def collect_stats(session: AsyncSession) -> dict[str, int]:
    """Aggregate counters for the ``/stats`` admin command."""
    active_groups = await session.scalar(
        select(func.count()).select_from(Group).where(Group.is_active.is_(True))
    )
    total_groups = await session.scalar(select(func.count()).select_from(Group))
    status_rows = await session.execute(
        select(NewsItem.status, func.count()).group_by(NewsItem.status)
    )
    stats = {
        "active_groups": active_groups or 0,
        "total_groups": total_groups or 0,
    }
    for status, count in status_rows.all():
        stats[f"news_{status}"] = count
    return stats
