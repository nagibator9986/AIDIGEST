"""Repository behaviour against a real (in-memory) database."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from app.db import repositories as repo
from app.db.base import AsyncSession
from app.db.models import NewsItem
from app.domain.enums import NewsStatus
from app.domain.schemas import RawItem
from app.utils.timeutil import utcnow

pytestmark = pytest.mark.asyncio


async def test_upsert_group_creates_then_reactivates(session: AsyncSession) -> None:
    group, created = await repo.upsert_group(
        session,
        chat_id=-100,
        title="Team",
        chat_type="supergroup",
        added_by=1,
        default_time="09:00",
        default_tz="UTC",
    )
    assert created is True
    await session.flush()
    # The product default: Monday + Friday only.
    assert group.digest_days == [1, 5]
    assert group.digest_times == ["09:00"]

    group.is_active = False
    await session.flush()

    group2, created2 = await repo.upsert_group(
        session,
        chat_id=-100,
        title="Team Renamed",
        chat_type="supergroup",
        added_by=1,
        default_time="09:00",
        default_tz="UTC",
    )
    assert created2 is False
    assert group2.is_active is True
    assert group2.title == "Team Renamed"


async def test_new_group_added_after_slot_skips_today(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Added on a delivery day at 15:00, past the 09:00 slot — it must not
    # fire within the minute; the next scheduled day gets the first digest.
    monkeypatch.setattr(repo, "now_in", lambda _tz: datetime(2026, 5, 22, 15, 0))
    group, created = await repo.upsert_group(
        session,
        chat_id=-200,
        title="Late",
        chat_type="group",
        added_by=1,
        default_time="09:00",
        default_tz="UTC",
    )
    assert created is True
    assert group.last_digest_on == date(2026, 5, 22)


async def test_new_group_added_before_slot_gets_today(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Added at 06:00 with a 09:00 slot — eligible for today's digest.
    monkeypatch.setattr(repo, "now_in", lambda _tz: datetime(2026, 5, 22, 6, 0))
    group, _ = await repo.upsert_group(
        session,
        chat_id=-201,
        title="Early",
        chat_type="group",
        added_by=1,
        default_time="09:00",
        default_tz="UTC",
    )
    assert group.last_digest_on is None


async def test_insert_raw_item_and_detect_existing_url(session: AsyncSession) -> None:
    item = RawItem(title="Story", url="https://example.com/post", source="rss")
    await repo.insert_raw_item(session, item)
    await session.flush()

    existing = await repo.get_existing_normalized_urls(
        session, [item.normalized_url, "https://example.com/other"]
    )
    assert existing == {item.normalized_url}


async def test_select_digest_items_orders_by_score(session: AsyncSession) -> None:
    now = utcnow()
    for idx, score in enumerate((7, 10, 8)):
        session.add(
            NewsItem(
                title=f"Item {idx}",
                source_url=f"https://example.com/{idx}",
                normalized_url=f"https://example.com/{idx}",
                source="rss",
                status=NewsStatus.APPROVED,
                score=score,
                scored_at=now,
                created_at=now,
            )
        )
    # Stale item — ingested outside the lookback window, must be excluded.
    session.add(
        NewsItem(
            title="Stale",
            source_url="https://example.com/stale",
            normalized_url="https://example.com/stale",
            source="rss",
            status=NewsStatus.APPROVED,
            score=10,
            scored_at=now,
            created_at=now - timedelta(days=30),
        )
    )
    await session.flush()

    picked = await repo.select_digest_items(session, lookback_days=7, threshold=7, limit=5)
    assert [i.score for i in picked] == [10, 8, 7]


async def test_mark_posted_advances_status(session: AsyncSession) -> None:
    item = await repo.insert_raw_item(
        session, RawItem(title="X", url="https://x.com/p", source="rss")
    )
    await session.flush()
    await repo.mark_posted(session, [item.id])
    await session.refresh(item)
    assert item.status == NewsStatus.POSTED
    assert item.posted_at is not None


async def _make_group(session: AsyncSession, chat_id: int) -> None:
    await repo.upsert_group(
        session,
        chat_id=chat_id,
        title="G",
        chat_type="group",
        added_by=1,
        default_time="09:00",
        default_tz="UTC",
    )
    await session.flush()


async def test_set_digest_times_replaces_schedule(session: AsyncSession) -> None:
    await _make_group(session, -500)
    assert await repo.set_digest_times(session, -500, ["08:00", "20:00"]) is True
    group = await repo.get_group(session, -500)
    assert group is not None
    assert group.digest_times == ["08:00", "20:00"]


async def test_set_digest_days_replaces_schedule(session: AsyncSession) -> None:
    await _make_group(session, -503)
    assert await repo.set_digest_days(session, -503, [1, 3, 5]) is True
    group = await repo.get_group(session, -503)
    assert group is not None
    assert group.digest_days == [1, 3, 5]


async def test_set_digest_times_marks_past_slots_as_consumed(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repo, "now_in", lambda _tz: datetime(2026, 5, 22, 6, 0))
    await _make_group(session, -504)

    monkeypatch.setattr(repo, "now_in", lambda _tz: datetime(2026, 5, 22, 15, 0))
    assert await repo.set_digest_times(session, -504, ["08:00", "20:00"]) is True
    group = await repo.get_group(session, -504)
    assert group is not None
    assert group.last_digest_on == date(2026, 5, 22)
    assert group.sent_slots_today == ["08:00"]


async def test_set_digest_days_resets_state_when_today_is_disabled(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repo, "now_in", lambda _tz: datetime(2026, 5, 21, 6, 0))
    await _make_group(session, -505)

    monkeypatch.setattr(repo, "now_in", lambda _tz: datetime(2026, 5, 21, 15, 0))
    assert await repo.set_digest_days(session, -505, [1, 3, 5]) is True
    group = await repo.get_group(session, -505)
    assert group is not None
    assert group.last_digest_on is None
    assert group.sent_slots_today == []


async def test_set_timezone_recomputes_passed_slots(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        repo,
        "now_in",
        lambda tz: datetime(2026, 5, 22, 6, 0) if tz == "UTC" else datetime(2026, 5, 22, 12, 0),
    )
    await _make_group(session, -506)

    assert await repo.set_timezone(session, -506, "Asia/Almaty") is True
    group = await repo.get_group(session, -506)
    assert group is not None
    assert group.last_digest_on == date(2026, 5, 22)
    assert group.sent_slots_today == ["09:00"]


async def test_set_digest_times_unknown_chat(session: AsyncSession) -> None:
    assert await repo.set_digest_times(session, -999, ["09:00"]) is False


async def test_set_paused_and_timezone(session: AsyncSession) -> None:
    await _make_group(session, -501)
    assert await repo.set_paused(session, -501, True) is True
    assert await repo.set_timezone(session, -501, "Asia/Almaty") is True
    group = await repo.get_group(session, -501)
    assert group is not None
    assert group.digest_paused is True
    assert group.timezone == "Asia/Almaty"


async def test_set_message_thread_routes_digest_to_topic(session: AsyncSession) -> None:
    await _make_group(session, -508)

    assert await repo.set_message_thread(session, -508, 12345) is True
    group = await repo.get_group(session, -508)
    assert group is not None
    assert group.message_thread_id == 12345

    assert await repo.set_message_thread(session, -508, None) is True
    assert group.message_thread_id is None


async def test_set_message_thread_unknown_chat(session: AsyncSession) -> None:
    assert await repo.set_message_thread(session, -999, 12345) is False


async def test_resume_premarks_past_slots(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repo, "now_in", lambda _tz: datetime(2026, 5, 22, 6, 0))
    await _make_group(session, -507)
    assert await repo.set_paused(session, -507, True) is True

    monkeypatch.setattr(repo, "now_in", lambda _tz: datetime(2026, 5, 22, 15, 0))
    assert await repo.set_paused(session, -507, False) is True
    group = await repo.get_group(session, -507)
    assert group is not None
    assert group.digest_paused is False
    assert group.last_digest_on == date(2026, 5, 22)
    assert group.sent_slots_today == ["09:00"]


async def test_mark_slot_sent_tracks_and_resets(session: AsyncSession) -> None:
    await _make_group(session, -502)
    day1, day2 = date(2026, 5, 21), date(2026, 5, 22)

    await repo.mark_slot_sent(session, -502, day1, "09:00")
    await repo.mark_slot_sent(session, -502, day1, "18:00")
    group = await repo.get_group(session, -502)
    assert group is not None
    assert group.last_digest_on == day1
    assert group.sent_slots_today == ["09:00", "18:00"]

    # A new local date resets the per-day slot list.
    await repo.mark_slot_sent(session, -502, day2, "09:00")
    group = await repo.get_group(session, -502)
    assert group is not None
    assert group.last_digest_on == day2
    assert group.sent_slots_today == ["09:00"]


async def test_list_unscored_diversifies_across_sources(
    session: AsyncSession,
) -> None:
    # A source-skewed pool (10 HF, 3 GitHub, 2 HN) must not yield an
    # all-HuggingFace scoring queue.
    for source, count in (("huggingface", 10), ("github", 3), ("hackernews", 2)):
        for i in range(count):
            session.add(
                NewsItem(
                    title=f"{source}{i}",
                    source_url=f"https://{source}/{i}",
                    normalized_url=f"https://{source}/{i}",
                    source=source,
                    status=NewsStatus.RAW,
                )
            )
    await session.flush()

    picked = await repo.list_unscored(session, limit=6)
    assert len(picked) == 6
    # All three sources are represented — the queue is interleaved.
    assert {item.source for item in picked} == {"huggingface", "github", "hackernews"}


async def test_collect_stats(session: AsyncSession) -> None:
    await repo.upsert_group(
        session,
        chat_id=-1,
        title="G",
        chat_type="group",
        added_by=1,
        default_time="09:00",
        default_tz="UTC",
    )
    await repo.insert_raw_item(session, RawItem(title="N", url="https://n.com", source="rss"))
    await session.flush()
    stats = await repo.collect_stats(session)
    assert stats["active_groups"] == 1
    assert stats["news_raw"] == 1
