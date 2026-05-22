"""GitHub Trending collector.

GitHub exposes no official trending API, so we parse the public HTML page.
The parser is defensive: layout changes degrade gracefully to an empty list
rather than crashing the ingestion cycle.
"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from app.collectors.base import Collector
from app.domain.schemas import RawItem
from app.utils.text import is_ai_relevant

_LANGUAGES = ("python", "typescript", "jupyter-notebook")
# Both windows: "weekly" surfaces what is genuinely popular, "daily" catches
# fast risers. Results are de-duplicated by repo URL.
_PERIODS = ("weekly", "daily")
_BASE = "https://github.com/trending/{lang}?since={since}"


class GitHubTrendingCollector(Collector):
    name = "github"

    async def collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        items: dict[str, RawItem] = {}
        for lang in _LANGUAGES:
            for period in _PERIODS:
                for item in await self._collect_language(client, lang, period):
                    items.setdefault(item.url, item)  # dedup across lang/period
        return list(items.values())

    async def _collect_language(
        self, client: httpx.AsyncClient, lang: str, period: str
    ) -> list[RawItem]:
        response = await client.get(
            _BASE.format(lang=lang, since=period),
            headers={"Accept": "text/html"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        results: list[RawItem] = []
        for row in soup.select("article.Box-row"):
            link = row.select_one("h2 a")
            if link is None:
                continue
            repo = str(link.get("href") or "").strip("/")
            if not repo:
                continue
            url = f"https://github.com/{repo}"

            desc_el = row.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            stars_today = ""
            star_el = row.select_one("span.d-inline-block.float-sm-right")
            if star_el:
                stars_today = star_el.get_text(strip=True)

            if not is_ai_relevant(repo, description):
                continue

            results.append(
                RawItem(
                    title=repo,
                    url=url,
                    source=self.name,
                    raw_content=(
                        f"GitHub trending {lang} repository. {description} ({stars_today})."
                    ).strip(),
                    external_id=repo,
                )
            )
        return results
