"""Collector registry — the single place that decides which sources run."""

from __future__ import annotations

from app.collectors.base import Collector
from app.collectors.github_trending import GitHubTrendingCollector
from app.collectors.hackernews import HackerNewsCollector
from app.collectors.huggingface import HuggingFaceCollector
from app.collectors.producthunt import ProductHuntCollector
from app.collectors.reddit import RedditCollector
from app.collectors.rss import RssCollector


def build_collectors() -> list[Collector]:
    """Return the active collector set for an ingestion cycle."""
    collectors: list[Collector] = [
        RssCollector(),  # tier 1 — first-party vendor announcements
        HackerNewsCollector(),  # tier 2 — engineer-vetted discussion
        RedditCollector(),  # tier 2 — open-source tooling chatter
        HuggingFaceCollector(),  # tier 1 — open-source research
        GitHubTrendingCollector(),  # tier 3 — trending tools
    ]
    if ProductHuntCollector.is_enabled():
        collectors.append(ProductHuntCollector())  # tier 3 — product launches
    return collectors
