"""Operator commands for bot admins (private chat only).

Gated by :class:`~app.bot.filters.IsBotAdmin` — every command in this router
requires the caller's id to be listed in ``ADMIN_IDS``.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from app.bot import texts
from app.bot.filters import IsBotAdmin
from app.db import repositories as repo
from app.db.base import AsyncSession
from app.logging import get_logger
from app.services.delivery import run_breaking_deliveries
from app.services.ingestion import run_ingestion
from app.services.scoring import run_scoring

router = Router(name="admin")
router.message.filter(F.chat.type == "private", IsBotAdmin())
log = get_logger(__name__)


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    """Show pool and subscriber statistics."""
    stats = await repo.collect_stats(session)
    news_lines = (
        "\n".join(
            f"  • {key.removeprefix('news_')}: <b>{value}</b>"
            for key, value in sorted(stats.items())
            if key.startswith("news_")
        )
        or "  • пул пуст"
    )
    await message.answer(
        texts.ADMIN_STATS.format(
            active_groups=stats.get("active_groups", 0),
            total_groups=stats.get("total_groups", 0),
            news_lines=news_lines,
        ),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("run_ingest"))
async def cmd_run_ingest(message: Message) -> None:
    """Trigger an ingestion cycle on demand."""
    await message.answer(
        texts.ADMIN_RUN_STARTED.format(task="сбор новостей"),
        parse_mode=ParseMode.HTML,
    )
    report = await run_ingestion()
    await message.answer(texts.ADMIN_INGEST_DONE.format(summary=report.summary))


@router.message(Command("run_scoring"))
async def cmd_run_scoring(message: Message, bot: Bot) -> None:
    """Trigger a scoring cycle on demand and push any urgent items."""
    await message.answer(
        texts.ADMIN_RUN_STARTED.format(task="скоринг через Gemini"),
        parse_mode=ParseMode.HTML,
    )
    report = await run_scoring()
    await message.answer(texts.ADMIN_SCORING_DONE.format(summary=report.summary))
    if report.breaking_item_ids:
        await run_breaking_deliveries(bot, report.breaking_item_ids)
