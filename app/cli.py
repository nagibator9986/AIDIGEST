"""Operational CLI — run individual pipeline stages by hand.

    python -m app.cli ingest    # one collection + dedup cycle
    python -m app.cli score     # one Gemini scoring cycle
    python -m app.cli digest    # build today's digest and broadcast it now

Useful for first-run seeding, debugging and cron-free operation.
"""

from __future__ import annotations

import argparse
import asyncio

# Configure logging before importing modules that create loggers — see the
# note in app.logging.get_logger. Hence the deliberate E402 imports below.
from app.config import get_settings
from app.logging import configure_logging

_settings = get_settings()
configure_logging(level=_settings.log_level, json_output=_settings.log_json)

from app.bot.factory import create_bot  # noqa: E402
from app.db import repositories as repo  # noqa: E402
from app.db.base import dispose_engine, session_scope  # noqa: E402
from app.domain.enums import DeliveryStatus  # noqa: E402
from app.logging import get_logger  # noqa: E402
from app.services.broadcaster import Broadcaster  # noqa: E402
from app.services.delivery import run_breaking_deliveries  # noqa: E402
from app.services.digest import build_digest_content  # noqa: E402
from app.services.ingestion import run_ingestion  # noqa: E402
from app.services.scoring import run_scoring  # noqa: E402
from app.utils.timeutil import now_in  # noqa: E402

log = get_logger(__name__)


async def _cmd_ingest() -> None:
    report = await run_ingestion()
    print(f"Ingestion: {report.summary}")


async def _cmd_score() -> None:
    report = await run_scoring()
    print(f"Scoring: {report.summary}")
    if report.breaking_item_ids:
        bot = create_bot()
        try:
            breaking = await run_breaking_deliveries(bot, report.breaking_item_ids)
            print(
                "Breaking delivery: "
                f"items {breaking.sent_items}/{breaking.candidates}, "
                f"sent chats {breaking.sent_chats}, "
                f"failed chats {breaking.failed_chats}, "
                f"blocked chats {breaking.blocked_chats}"
            )
        finally:
            await bot.session.close()


async def _cmd_digest() -> None:
    settings = get_settings()
    local_date = now_in(settings.timezone).date()
    content = await build_digest_content(local_date)

    async with session_scope() as session:
        groups = await repo.list_active_groups(session)

    if not groups:
        print("Digest built, but there are no active chats to deliver to.")
        return

    bot = create_bot()
    try:
        broadcaster = Broadcaster(bot)
        result = await broadcaster.deliver_digest(
            content.header, content.cards, [g.id for g in groups]
        )
        # A manual broadcast does not consume any chat's scheduled slot.
        async with session_scope() as session:
            for chat_id in result.sent:
                await repo.log_delivery(
                    session,
                    group_id=chat_id,
                    digest_date=local_date,
                    item_count=len(content.item_ids),
                    status=DeliveryStatus.SENT,
                )
    finally:
        await bot.session.close()
    print(
        f"Digest ({len(content.item_ids)} items): "
        f"sent {len(result.sent)}, failed {len(result.failed)}, "
        f"blocked {len(result.blocked)}"
    )


_COMMANDS = {
    "ingest": _cmd_ingest,
    "score": _cmd_score,
    "digest": _cmd_digest,
}


async def _run(command: str) -> None:
    try:
        await _COMMANDS[command]()
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__)
    parser.add_argument("command", choices=sorted(_COMMANDS))
    args = parser.parse_args()
    asyncio.run(_run(args.command))


if __name__ == "__main__":
    main()
