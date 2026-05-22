"""RSS/Atom collector for first-party vendor blogs.

Vendor blogs are the highest-signal source for model releases — when OpenAI or
Google DeepMind publishes, it is news by definition. Feeds are fetched with
httpx and parsed with feedparser (run off-thread, since feedparser is sync).
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

# Curated, high-signal feeds. Unreachable feeds are skipped, never fatal.
_DEFAULT_FEEDS: dict[str, str] = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Meta AI": "https://ai.meta.com/blog/rss/",
    "BAIR Berkeley": "https://bair.berkeley.edu/blog/feed.xml",
}


class RssCollector(Collector):
    name = "rss"

    async def collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        feeds = dict(_DEFAULT_FEEDS)
        for extra in get_settings().extra_rss_feeds:
            feeds[extra] = extra

        tasks = [self._collect_feed(client, label, url) for label, url in feeds.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
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
        for entry in feed.entries[:40]:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            if not title or not link:
                continue
            published = _entry_datetime(entry)
            if published and published.timestamp() < cutoff:
                continue
            summary = clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
            # Vendor feeds are trusted; mixed feeds still get a relevance gate.
            if label not in _DEFAULT_FEEDS and not is_ai_relevant(title, summary):
                continue
            items.append(
                RawItem(
                    title=title,
                    url=link,
                    source=self.name,
                    raw_content=f"Official blog post from {label}. {summary}".strip(),
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
