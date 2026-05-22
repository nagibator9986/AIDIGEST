"""Ingestion service — stage 1 & 2 of the pipeline (collect + deduplicate).

Runs every ``INGEST_INTERVAL_HOURS`` hours. Collectors run concurrently and in
isolation; whatever survives deduplication is persisted with ``RAW`` status,
ready for the scoring stage.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from app.collectors.base import make_http_client
from app.collectors.registry import build_collectors
from app.config import get_settings
from app.db import repositories as repo
from app.db.base import session_scope
from app.logging import get_logger
from app.services.dedup import dedup_within_batch, find_title_duplicate
from app.utils.timeutil import utcnow

log = get_logger(__name__)


@dataclass(slots=True)
class IngestionReport:
    """Outcome of one ingestion cycle."""

    collected: int = 0
    new: int = 0
    url_duplicates: int = 0
    title_duplicates: int = 0

    @property
    def summary(self) -> str:
        return (
            f"собрано {self.collected}, новых {self.new}, "
            f"дублей по URL {self.url_duplicates}, "
            f"дублей по заголовку {self.title_duplicates}"
        )


async def run_ingestion() -> IngestionReport:
    """Execute one full ingestion cycle and return a report."""
    report = IngestionReport()
    collectors = build_collectors()

    async with make_http_client() as client:
        batches = await asyncio.gather(*(c.safe_collect(client) for c in collectors))

    raw_items = [item for batch in batches for item in batch]
    report.collected = len(raw_items)
    if not raw_items:
        log.info("ingestion.empty")
        return report

    unique = dedup_within_batch(raw_items)
    report.url_duplicates += report.collected - len(unique)

    settings = get_settings()
    async with session_scope() as session:
        # Layer 1: drop URLs already in the pool.
        existing = await repo.get_existing_normalized_urls(
            session, [it.normalized_url for it in unique]
        )
        fresh = [it for it in unique if it.normalized_url not in existing]
        report.url_duplicates += len(unique) - len(fresh)

        # Layer 2: fuzzy title match against the recent window.
        since = utcnow() - timedelta(days=settings.lookback_days)
        known = await repo.recent_titles(session, since=since)

        for item in fresh:
            twin = find_title_duplicate(item.title, known)
            if twin is not None:
                await repo.add_extra_source(session, twin, item.url)
                report.title_duplicates += 1
                continue
            news = await repo.insert_raw_item(session, item)
            await session.flush()  # assigns news.id for subsequent matches
            known.append((news.id, news.title))
            report.new += 1

    log.info(
        "ingestion.done",
        **{
            "collected": report.collected,
            "new": report.new,
            "url_dupes": report.url_duplicates,
            "title_dupes": report.title_duplicates,
        },
    )
    return report
