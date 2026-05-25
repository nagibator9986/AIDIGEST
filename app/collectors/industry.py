"""Industry-applied AI news collector.

Banking, fintech, government and regtech publications. Most of these are not
AI-only feeds, so each entry is still passed through :func:`is_ai_relevant`
to weed out non-AI material. The point is to surface news the digest's
banking, fintech and government audience can act on — credit scoring,
fraud detection, KYC/AML, regtech, AI procurement and policy.
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

# Curated finance / public-sector feeds. AI-tagged channels first; general
# industry feeds afterwards (filtered downstream by `is_ai_relevant`).
_FEEDS: dict[str, str] = {
    "Finextra AI": "https://www.finextra.com/rss/channel.aspx?channel=artificial-intelligence",
    "PYMNTS AI": "https://www.pymnts.com/category/artificial-intelligence/feed/",
    "Banking Dive": "https://www.bankingdive.com/feeds/news/",
    "American Banker": "https://www.americanbanker.com/feed?rss=true",
    "The Fintech Times": "https://thefintechtimes.com/feed/",
    "NextGov Emerging Tech": "https://www.nextgov.com/rss/emerging-tech/",
    "FedScoop": "https://fedscoop.com/feed/",
    "StateScoop": "https://statescoop.com/feed/",
}


class IndustryNewsCollector(Collector):
    name = "industry"

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
            # General industry feeds — keep only AI-relevant stories.
            if not is_ai_relevant(title, summary):
                continue
            items.append(
                RawItem(
                    title=title,
                    url=link,
                    source=self.name,
                    raw_content=f"Отраслевая AI-новость от {label}. {summary}".strip(),
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
