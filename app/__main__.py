"""Application entry point.

Runs the aiogram long-polling loop and the APScheduler background jobs inside
a single asyncio event loop, with clean startup/shutdown hooks.

    python -m app
"""

from __future__ import annotations

import asyncio

# Logging is configured BEFORE importing any module that creates a logger:
# `get_logger()` realizes loggers eagerly, so a logger created pre-config
# would be frozen against structlog's defaults. Hence the deliberate E402s.
from app.config import get_settings
from app.logging import configure_logging

_settings = get_settings()
configure_logging(level=_settings.log_level, json_output=_settings.log_json)

from aiogram import Bot  # noqa: E402

from app import __version__  # noqa: E402
from app.bot.factory import (  # noqa: E402
    create_bot,
    create_dispatcher,
    setup_bot_commands,
)
from app.db.base import dispose_engine  # noqa: E402
from app.health import touch as heartbeat  # noqa: E402
from app.logging import get_logger  # noqa: E402
from app.scheduler.jobs import create_scheduler  # noqa: E402

log = get_logger(__name__)


async def run() -> None:
    """Wire everything together and run until interrupted."""
    settings = get_settings()
    log.info(
        "app.starting",
        version=__version__,
        model=settings.gemini_model,
        admins=len(settings.admin_ids),
    )

    bot = create_bot()
    dispatcher = create_dispatcher()
    scheduler = create_scheduler(bot)

    async def _on_startup(bot: Bot) -> None:
        me = await bot.get_me()
        await setup_bot_commands(bot)
        heartbeat()
        scheduler.start()
        log.info("app.started", bot=f"@{me.username}", id=me.id)

    async def _on_shutdown() -> None:
        log.info("app.stopping")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await dispose_engine()
        log.info("app.stopped")

    dispatcher.startup.register(_on_startup)
    dispatcher.shutdown.register(_on_shutdown)

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()


def main() -> None:
    """Synchronous wrapper used as the console-script / module entry point."""
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        log.info("app.interrupted")


if __name__ == "__main__":
    main()
