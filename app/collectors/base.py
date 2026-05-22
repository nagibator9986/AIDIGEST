"""Collector contract and a fault-tolerant runner.

Every collector is an isolated unit: a failure in one source must never abort
the ingestion cycle. :meth:`Collector.safe_collect` enforces that guarantee.
"""

from __future__ import annotations

import abc

import httpx

from app.config import get_settings
from app.domain.schemas import RawItem
from app.logging import get_logger

log = get_logger(__name__)


class Collector(abc.ABC):
    """Abstract source adapter.

    Subclasses set :attr:`name` (used as ``NewsItem.source``) and implement
    :meth:`collect`.
    """

    name: str = "base"

    @abc.abstractmethod
    async def collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        """Fetch and return fresh items. May raise — the runner isolates it."""
        raise NotImplementedError

    async def safe_collect(self, client: httpx.AsyncClient) -> list[RawItem]:
        """Run :meth:`collect`, swallowing and logging any failure."""
        try:
            items = await self.collect(client)
        except Exception as exc:
            log.warning("collector.failed", source=self.name, error=str(exc))
            return []
        # Drop anything without a usable URL or title.
        clean = [it for it in items if it.url and it.title]
        log.info("collector.done", source=self.name, items=len(clean))
        return clean


def make_http_client() -> httpx.AsyncClient:
    """Create an :class:`httpx.AsyncClient` configured for collectors."""
    settings = get_settings()
    return httpx.AsyncClient(
        timeout=settings.request_timeout,
        follow_redirects=True,
        headers={"User-Agent": settings.http_user_agent},
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
