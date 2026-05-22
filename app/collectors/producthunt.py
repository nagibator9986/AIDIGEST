"""Product Hunt collector (optional).

Enabled only when ``PRODUCTHUNT_TOKEN`` is set. Uses the GraphQL API to pull
the day's top posts and keeps those tagged with an AI-related topic.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.collectors.base import Collector
from app.config import get_settings
from app.domain.schemas import RawItem

_ENDPOINT = "https://api.producthunt.com/v2/api/graphql"
_QUERY = """
query TopPosts {
  posts(order: VOTES, first: 20) {
    edges {
      node {
        name
        tagline
        description
        url
        votesCount
        createdAt
        topics(first: 5) { edges { node { name } } }
      }
    }
  }
}
"""
_AI_TOPIC_HINTS = ("artificial intelligence", "ai ", "machine learning", "gpt", "llm")


class ProductHuntCollector(Collector):
    name = "producthunt"

    @staticmethod
    def is_enabled() -> bool:
        return get_settings().producthunt_token is not None

    async def collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        token = get_settings().producthunt_token
        if token is None:
            return []

        response = await client.post(
            _ENDPOINT,
            json={"query": _QUERY},
            headers={"Authorization": f"Bearer {token.get_secret_value()}"},
        )
        response.raise_for_status()
        edges = response.json().get("data", {}).get("posts", {}).get("edges", [])

        items: list[RawItem] = []
        for edge in edges:
            node = edge.get("node", {})
            topics = " ".join(
                t["node"]["name"].lower() for t in node.get("topics", {}).get("edges", [])
            )
            if not any(hint in topics + " " for hint in _AI_TOPIC_HINTS):
                continue
            name = node.get("name") or ""
            url = node.get("url") or ""
            if not name or not url:
                continue
            items.append(
                RawItem(
                    title=name,
                    url=url,
                    source=self.name,
                    raw_content=(
                        f"Product Hunt launch — {node.get('votesCount', 0)} votes. "
                        f"{node.get('tagline', '')}. {node.get('description', '')}"
                    ).strip(),
                    points=node.get("votesCount"),
                    published_at=_parse_dt(node.get("createdAt")),
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
