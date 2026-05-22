"""Reddit collector.

Reads the public ``top.json`` listing for a curated set of subreddits.
``r/LocalLLaMA`` is the best open-source-tooling signal there is; the others
are kept on a short leash with a per-subreddit score floor.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.collectors.base import Collector
from app.domain.schemas import RawItem
from app.utils.text import clean_html

# subreddit -> minimum upvotes to consider. A deliberate mix: developer-focused
# communities *and* broad-audience ones (products, tools, general AI news), so
# the digest serves a wide audience — not only programmers. Bigger, noisier
# subreddits carry a higher upvote floor.
_SUBREDDITS: dict[str, int] = {
    "LocalLLaMA": 80,        # open-source models & tooling
    "MachineLearning": 150,  # research & engineering
    "OpenAI": 200,           # product news, broad audience
    "artificial": 250,       # general AI discussion
    "ChatGPT": 600,          # mass-audience; high floor to cut noise
}


class RedditCollector(Collector):
    name = "reddit"

    async def collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        items: list[RawItem] = []
        for subreddit, min_score in _SUBREDDITS.items():
            items.extend(await self._collect_sub(client, subreddit, min_score))
        return items

    async def _collect_sub(
        self, client: httpx.AsyncClient, subreddit: str, min_score: int
    ) -> list[RawItem]:
        # "top of the week" — the most popular threads in the lookback window.
        response = await client.get(
            f"https://www.reddit.com/r/{subreddit}/top.json",
            params={"t": "week", "limit": 75},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        children = response.json().get("data", {}).get("children", [])

        results: list[RawItem] = []
        for child in children:
            post = child.get("data", {})
            score = post.get("score", 0)
            if score < min_score or post.get("stickied"):
                continue
            title = post.get("title") or ""
            permalink = post.get("permalink") or ""
            if not title or not permalink:
                continue
            selftext = clean_html(post.get("selftext", ""))[:1000]
            created = post.get("created_utc")

            results.append(
                RawItem(
                    title=title,
                    # Always link to the discussion, not the bare external URL.
                    url=f"https://www.reddit.com{permalink}",
                    source=self.name,
                    raw_content=(
                        f"r/{subreddit} discussion — {score} upvotes, "
                        f"{post.get('num_comments', 0)} comments. {selftext}"
                    ).strip(),
                    external_id=post.get("id"),
                    points=score,
                    published_at=(datetime.fromtimestamp(created, tz=UTC) if created else None),
                )
            )
        return results
