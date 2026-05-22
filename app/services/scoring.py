"""Scoring service — stage 3 of the pipeline (semantic filtering via Gemini).

Each RAW item is sent to Gemini, which returns a structured verdict. The
verdict drives a status transition:

* ``score < threshold`` -> REJECTED
* ``threshold .. 8``    -> APPROVED  (goes out by the chat schedule)
* ``9 .. 10``           -> BREAKING  (must be pushed immediately)

API calls already retry transient errors internally (see :class:`GeminiClient`);
an item that still fails has exhausted those retries, so it is marked FAILED
and excluded from later cycles. A failure on one item never blocks the others.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from app.config import get_settings
from app.db import repositories as repo
from app.db.base import session_scope
from app.db.models import NewsItem
from app.domain.enums import NewsStatus
from app.domain.schemas import GeminiVerdict
from app.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class ScoringReport:
    """Outcome of one scoring cycle."""

    scored: int = 0
    approved: int = 0
    breaking: int = 0
    rejected: int = 0
    failed: int = 0
    # Item ids that must bypass the group schedule and be sent right away.
    breaking_item_ids: list[uuid.UUID] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"оценено {self.scored}: по расписанию {self.approved}, "
            f"срочных {self.breaking}, отклонено {self.rejected}, "
            f"ошибок {self.failed}"
        )


def decide_status(verdict: GeminiVerdict) -> NewsStatus:
    """Map a Gemini verdict onto the next pipeline status."""
    settings = get_settings()
    threshold = settings.score_threshold

    if verdict.score < threshold:
        return NewsStatus.REJECTED
    if verdict.score > 8:
        return NewsStatus.BREAKING
    return NewsStatus.APPROVED


async def run_scoring(limit: int | None = None) -> ScoringReport:
    """Score the top RAW items and persist the verdicts.

    *limit* defaults to ``SCORING_BUDGET`` — the daily cap that keeps the bot
    within the Gemini free-tier quota. The most valuable items are scored first
    (see :func:`~app.db.repositories.list_unscored`).
    """
    report = ScoringReport()
    budget = limit if limit is not None else get_settings().scoring_budget

    # Phase 1 — read the work set, then release the connection.
    async with session_scope() as session:
        items = await repo.list_unscored(session, limit=budget)
        work = [(it.id, it.source, it.title, it.source_url, it.raw_content) for it in items]

    if not work:
        log.info("scoring.empty")
        return report

    # Phase 2 — score concurrently (GeminiClient caps real parallelism).
    from app.ai.gemini import GeminiClient

    gemini = GeminiClient()

    async def _score(payload: tuple[uuid.UUID, str, str, str, str]):
        item_id, source, title, url, content = payload
        return item_id, await gemini.score(source=source, title=title, url=url, content=content)

    results = await asyncio.gather(*(_score(p) for p in work), return_exceptions=True)

    # Phase 3 — persist verdicts and status transitions.
    async with session_scope() as session:
        for payload, result in zip(work, results, strict=True):
            item_id = payload[0]
            item: NewsItem | None = await repo.get_news(session, item_id)
            if item is None:
                continue
            if isinstance(result, BaseException):
                await repo.mark_failed(session, item)
                report.failed += 1
                log.warning("scoring.item_failed", item_id=str(item_id), error=str(result))
                continue

            _, verdict = result
            status = decide_status(verdict)
            await repo.apply_verdict(session, item, verdict, status=status)
            report.scored += 1
            if status is NewsStatus.APPROVED:
                report.approved += 1
            elif status is NewsStatus.BREAKING:
                report.breaking += 1
                report.breaking_item_ids.append(item_id)
            else:
                report.rejected += 1

    log.info(
        "scoring.done",
        scored=report.scored,
        approved=report.approved,
        breaking=report.breaking,
        rejected=report.rejected,
        failed=report.failed,
    )
    return report
