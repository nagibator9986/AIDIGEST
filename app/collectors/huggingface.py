"""Hugging Face Daily Papers collector.

Daily Papers is the most reliable single signal for open-source research that
practitioners actually care about; ``upvotes`` is used as the points proxy.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.collectors.base import Collector
from app.domain.schemas import RawItem

_API = "https://huggingface.co/api/daily_papers"


class HuggingFaceCollector(Collector):
    name = "huggingface"

    async def collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        response = await client.get(_API, params={"limit": 50})
        response.raise_for_status()
        payload = response.json()

        items: list[RawItem] = []
        for entry in payload:
            paper = entry.get("paper") or {}
            title = paper.get("title") or entry.get("title") or ""
            arxiv_id = paper.get("id") or ""
            if not title or not arxiv_id:
                continue
            summary = paper.get("summary") or entry.get("summary") or ""
            published_raw = entry.get("publishedAt") or paper.get("publishedAt")
            published = _parse_dt(published_raw)
            upvotes = paper.get("upvotes") or 0

            items.append(
                RawItem(
                    title=title,
                    url=f"https://huggingface.co/papers/{arxiv_id}",
                    source=self.name,
                    raw_content=f"Research paper (arXiv {arxiv_id}). {summary}".strip(),
                    external_id=arxiv_id,
                    points=upvotes,
                    published_at=published,
                )
            )
        return items


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
