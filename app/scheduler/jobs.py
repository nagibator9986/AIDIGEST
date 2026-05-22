"""Scheduled jobs and the APScheduler wiring.

Three recurring jobs make up the pipeline's heartbeat:

* **ingestion** — every ``INGEST_INTERVAL_HOURS`` hours.
* **scoring**   — daily, two hours before the default digest time, so the
  pool is fully scored before any chat is due.
* **delivery**  — every minute: pushes urgent items and fans out the digest to
  whichever chats have just reached their local delivery time.

Every job body is exception-isolated; a failure is logged and the schedule
continues uninterrupted.
"""

from __future__ import annotations

from datetime import timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.health import touch as heartbeat
from app.logging import get_logger
from app.services.delivery import run_breaking_deliveries, run_due_deliveries
from app.services.ingestion import run_ingestion
from app.services.scoring import run_scoring
from app.utils.timeutil import utcnow

log = get_logger(__name__)


async def job_ingestion() -> None:
    """Collect + deduplicate fresh news."""
    try:
        report = await run_ingestion()
        log.info("job.ingestion.ok", summary=report.summary)
    except Exception as exc:
        log.error("job.ingestion.failed", error=str(exc), exc_info=True)


async def job_scoring(_bot: Bot) -> None:
    """Score the RAW pool through Gemini."""
    try:
        report = await run_scoring()
        log.info("job.scoring.ok", summary=report.summary)
    except Exception as exc:
        log.error("job.scoring.failed", error=str(exc), exc_info=True)


async def job_delivery(bot: Bot) -> None:
    """Per-minute tick: push urgent items, then deliver due digests."""
    heartbeat()  # liveness signal for the container healthcheck
    try:
        breaking = await run_breaking_deliveries(bot)
        report = await run_due_deliveries(bot)
        if breaking.candidates or report.due_chats:
            log.info(
                "job.delivery.ok",
                urgent_candidates=breaking.candidates,
                urgent_sent_items=breaking.sent_items,
                due=report.due_chats,
                sent=report.sent,
                skipped=report.skipped,
                failed=report.failed,
                blocked=report.blocked,
            )
    except Exception as exc:
        log.error("job.delivery.failed", error=str(exc), exc_info=True)


def _scoring_trigger() -> CronTrigger:
    """Daily cron, two hours before the default digest time."""
    settings = get_settings()
    digest = settings.default_digest_time
    hour = (digest.hour - 2) % 24
    return CronTrigger(hour=hour, minute=digest.minute, timezone=settings.tz)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Build and configure (but do not start) the application scheduler."""
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.tz)

    common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 300}

    # First ingestion fires ~30 s after startup so the pool fills immediately.
    scheduler.add_job(
        job_ingestion,
        trigger=IntervalTrigger(hours=settings.ingest_interval_hours),
        id="ingestion",
        next_run_time=utcnow() + timedelta(seconds=30),
        **common,
    )
    scheduler.add_job(
        job_scoring,
        trigger=_scoring_trigger(),
        id="scoring",
        args=[bot],
        **common,
    )
    scheduler.add_job(
        job_delivery,
        trigger=IntervalTrigger(minutes=1),
        id="delivery",
        args=[bot],
        **common,
    )

    log.info(
        "scheduler.configured",
        ingest_every_h=settings.ingest_interval_hours,
        scoring_at=str(_scoring_trigger()),
        digest_default=settings.digest_time,
    )
    return scheduler
