"""Tech-press AI news collector.

Broad-audience AI coverage from major technology publications — the kind of
practical AI news (tools, products, courses, industry shifts) that
professionals actually follow and share. Reliable RSS, no authentication.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import struct_time

import feedparser
import httpx

from app.collectors.base import Collector
from app.config import get_settings
from app.domain.schemas import RawItem
from app.utils.text import clean_html, is_ai_relevant

# Curated AI / tech-press feeds. Unreachable feeds are skipped, never fatal.
_FEEDS: dict[str, str] = {
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
    "MarkTechPost": "https://www.marktechpost.com/feed/",
    "AI News": "https://www.artificialintelligence-news.com/feed/",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}


class TechNewsCollector(Collector):
    name = "technews"

    async def collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        results = await asyncio.gather(
            *(self._collect_feed(client, label, url) for label, url in _FEEDS.items()),
            return_exceptions=True,
        )
        items: list[RawItem] = []
        for result in results:
            if isinstance(result, list):
                items.extend(result)
        return items

    async def _collect_feed(self, client: httpx.AsyncClient, label: str, url: str) -> list[RawItem]:
        try:
            response = await client.get(url, headers={"Accept": "application/rss+xml"})
            response.raise_for_status()
        except httpx.HTTPError:
            return []

        feed = await asyncio.to_thread(feedparser.parse, response.content)
        cutoff = datetime.now(UTC).timestamp() - get_settings().lookback_seconds

        items: list[RawItem] = []
        for entry in feed.entries[:30]:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            if not title or not link:
                continue
            published = _entry_datetime(entry)
            if published and published.timestamp() < cutoff:
                continue
            summary = clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
            # These are general tech feeds — keep only AI-relevant stories.
            if not is_ai_relevant(title, summary):
                continue
            items.append(
                RawItem(
                    title=title,
                    url=link,
                    source=self.name,
                    raw_content=f"AI-новость от {label}. {summary}".strip(),
                    external_id=getattr(entry, "id", None) or link,
                    published_at=published,
                )
            )
        return items


def _entry_datetime(entry: object) -> datetime | None:
    parsed: struct_time | None = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if parsed is None:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)
