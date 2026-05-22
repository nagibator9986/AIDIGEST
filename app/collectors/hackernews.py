"""Hacker News collector via the Algolia HN Search API.

The score threshold (``HN_MIN_SCORE``) is the single best anti-hype filter we
have: a story that organically clears 100+ points on HN is, by construction,
something engineers found genuinely worth discussing.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.collectors.base import Collector
from app.config import get_settings
from app.domain.schemas import RawItem
from app.utils.text import is_ai_relevant

# The `search` endpoint (vs `search_by_date`) ranks hits by Algolia's
# popularity formula — exactly what we want for "the most popular stories".
_API = "https://hn.algolia.com/api/v1/search"


class HackerNewsCollector(Collector):
    name = "hackernews"

    async def collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        settings = get_settings()
        since = int(datetime.now(UTC).timestamp() - settings.lookback_seconds)
        response = await client.get(
            _API,
            params={
                "tags": "story",
                "numericFilters": f"created_at_i>{since},points>={settings.hn_min_score}",
                "hitsPerPage": 100,
            },
        )
        response.raise_for_status()
        hits = response.json().get("hits", [])

        items: list[RawItem] = []
        for hit in hits:
            title = hit.get("title") or ""
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
            story_text = hit.get("story_text") or ""
            if not title:
                continue
            # Only stories that are actually about AI/ML.
            if not is_ai_relevant(title, url, story_text):
                continue
            published = (
                datetime.fromtimestamp(hit["created_at_i"], tz=UTC)
                if hit.get("created_at_i")
                else None
            )
            items.append(
                RawItem(
                    title=title,
                    url=url,
                    source=self.name,
                    raw_content=(
                        f"Hacker News story — {hit.get('points', 0)} points, "
                        f"{hit.get('num_comments', 0)} comments. {story_text}"
                    ).strip(),
                    external_id=str(hit["objectID"]),
                    points=hit.get("points"),
                    published_at=published,
                )
            )
        return items
