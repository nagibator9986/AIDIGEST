"""Construction of the aiogram :class:`Bot` and :class:`Dispatcher`.

Middleware order matters. ``ErrorLoggingMiddleware`` is registered first so it
sits *outside* ``DbSessionMiddleware``: a handler exception first triggers a
transaction rollback, then gets logged — never crashing the dispatcher.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from app.bot.handlers import admin, chat_member, commands, settings
from app.bot.middlewares import DbSessionMiddleware, ErrorLoggingMiddleware
from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

_PRIVATE_COMMANDS = [
    BotCommand(command="start", description="О боте"),
    BotCommand(command="help", description="Справка и возможности"),
]
_GROUP_COMMANDS = [
    BotCommand(command="settings", description="⚙️ Панель настроек дайджеста"),
    BotCommand(command="digest_time", description="Время доставки (1–8 раз/день)"),
    BotCommand(command="digest_days", description="Дни отправки плановых новостей"),
    BotCommand(command="timezone", description="Часовой пояс чата"),
    BotCommand(command="digest_now", description="Прислать дайджест сейчас"),
    BotCommand(command="help", description="Справка"),
]


def create_bot() -> Bot:
    """Create the configured :class:`Bot` instance."""
    return Bot(
        token=get_settings().bot_token.get_secret_value(),
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )


def create_dispatcher() -> Dispatcher:
    """Create the :class:`Dispatcher` with middlewares and routers wired up."""
    dp = Dispatcher()

    # Outer -> inner.
    dp.update.outer_middleware(ErrorLoggingMiddleware())
    dp.update.middleware(DbSessionMiddleware())

    # Specific routers first; the generic command router last.
    dp.include_router(chat_member.router)
    dp.include_router(settings.router)
    dp.include_router(admin.router)
    dp.include_router(commands.router)

    log.debug("dispatcher.created", routers=len(dp.sub_routers))
    return dp


async def setup_bot_commands(bot: Bot) -> None:
    """Publish the slash-command menus for private and group chats."""
    await bot.set_my_commands(_PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(_GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
