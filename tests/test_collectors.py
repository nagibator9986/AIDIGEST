"""Collector parsing — verified against mocked HTTP responses."""

from __future__ import annotations

import httpx
import pytest

respx = pytest.importorskip("respx")

from app.collectors.base import make_http_client  # noqa: E402
from app.collectors.github_trending import GitHubTrendingCollector  # noqa: E402
from app.collectors.hackernews import HackerNewsCollector  # noqa: E402

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_hackernews_keeps_only_ai_stories() -> None:
    respx.get(url__startswith="https://hn.algolia.com").mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "1",
                        "title": "New open-source LLM beats GPT-4",
                        "url": "https://example.com/llm",
                        "points": 320,
                        "num_comments": 90,
                        "created_at_i": 1_900_000_000,
                    },
                    {
                        "objectID": "2",
                        "title": "A faster CSS grid layout trick",
                        "url": "https://example.com/css",
                        "points": 250,
                        "num_comments": 40,
                        "created_at_i": 1_900_000_000,
                    },
                ]
            },
        )
    )
    async with make_http_client() as client:
        items = await HackerNewsCollector().collect(client)

    assert len(items) == 1
    assert items[0].source == "hackernews"
    assert items[0].points == 320
    assert "LLM" in items[0].title


@respx.mock
async def test_hackernews_failure_is_isolated() -> None:
    respx.get(url__startswith="https://hn.algolia.com").mock(return_value=httpx.Response(500))
    async with make_http_client() as client:
        # safe_collect must swallow the error and yield an empty list.
        items = await HackerNewsCollector().safe_collect(client)
    assert items == []


_TRENDING_HTML = """
<html><body>
  <article class="Box-row">
    <h2><a href="/acme/llm-agent-kit">acme / llm-agent-kit</a></h2>
    <p>A toolkit for building autonomous LLM agents with RAG.</p>
    <span class="d-inline-block float-sm-right">120 stars today</span>
  </article>
  <article class="Box-row">
    <h2><a href="/acme/css-helper">acme / css-helper</a></h2>
    <p>Tiny CSS utility library.</p>
  </article>
</body></html>
"""


@respx.mock
async def test_github_trending_filters_by_relevance() -> None:
    respx.get(url__startswith="https://github.com/trending").mock(
        return_value=httpx.Response(200, text=_TRENDING_HTML)
    )
    async with make_http_client() as client:
        items = await GitHubTrendingCollector().collect(client)

    urls = {it.url for it in items}
    assert "https://github.com/acme/llm-agent-kit" in urls
    assert "https://github.com/acme/css-helper" not in urls
