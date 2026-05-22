"""User-facing commands: /start, /help, /settings, /status, /digest_now,
/digest_time, /digest_days, /timezone.

The chat-management commands are registered on both the ``message`` and
``channel_post`` observers: a command typed inside a channel arrives as a
``channel_post`` update, not a ``message``, so a message-only handler would
never see it.
"""

from __future__ import annotations

import html
import zoneinfo

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.bot import texts
from app.bot.filters import is_authorized_operator, is_managed_chat
from app.bot.panels import plural_times, render_settings_panel
from app.bot.schedule import format_weekdays
from app.config import normalize_schedule, normalize_weekdays
from app.db import repositories as repo
from app.db.base import AsyncSession
from app.logging import get_logger
from app.services.delivery import deliver_now

router = Router(name="commands")
log = get_logger(__name__)


@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message) -> None:
    await message.answer(texts.START_PRIVATE, parse_mode=ParseMode.HTML)


@router.message(Command("help"))
@router.channel_post(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP, parse_mode=ParseMode.HTML)


@router.message(Command("settings", "status"))
@router.channel_post(Command("settings", "status"))
async def cmd_settings(message: Message, session: AsyncSession) -> None:
    """Show the interactive digest-settings panel."""
    if not is_managed_chat(message):
        await message.answer(texts.NOT_GROUP)
        return
    group = await repo.get_group(session, message.chat.id)
    if group is None:
        await message.answer(texts.GROUP_UNKNOWN, parse_mode=ParseMode.HTML)
        return
    text, keyboard = render_settings_panel(group)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.message(Command("digest_now"))
@router.channel_post(Command("digest_now"))
async def cmd_digest_now(message: Message, bot: Bot) -> None:
    """Force-deliver a digest to this chat (chat admins only)."""
    if not is_managed_chat(message):
        await message.answer(texts.NOT_GROUP)
        return
    if not await is_authorized_operator(bot, message):
        await message.answer(texts.NOT_CHAT_ADMIN, parse_mode=ParseMode.HTML)
        return

    notice = await message.answer(texts.DIGEST_SENDING)
    ok, count = await deliver_now(bot, message.chat.id)
    text = texts.DIGEST_SENT.format(count=count) if ok else texts.DIGEST_FAILED
    try:
        await notice.edit_text(text)
    except Exception:
        await message.answer(text)


@router.message(Command("digest_time"))
@router.channel_post(Command("digest_time"))
async def cmd_digest_time(
    message: Message, command: CommandObject, bot: Bot, session: AsyncSession
) -> None:
    """Set this chat's delivery schedule — one or more ``HH:MM`` slots."""
    if not is_managed_chat(message):
        await message.answer(texts.NOT_GROUP)
        return
    if not await is_authorized_operator(bot, message):
        await message.answer(texts.NOT_CHAT_ADMIN, parse_mode=ParseMode.HTML)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(texts.DIGEST_TIME_USAGE, parse_mode=ParseMode.HTML)
        return
    try:
        # Accept space- or comma-separated values.
        times = normalize_schedule(raw.replace(",", " ").split())
    except ValueError:
        await message.answer(texts.DIGEST_TIME_BAD, parse_mode=ParseMode.HTML)
        return

    if not await repo.set_digest_times(session, message.chat.id, times):
        await message.answer(texts.GROUP_UNKNOWN, parse_mode=ParseMode.HTML)
        return

    group = await repo.get_group(session, message.chat.id)
    tz = group.timezone if group else ""
    log.info("group.schedule_changed", chat_id=message.chat.id, times=times)
    await message.answer(
        texts.DIGEST_TIME_OK.format(
            times=html.escape(", ".join(times)),
            freq=plural_times(len(times)),
            tz=html.escape(tz),
        ),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("digest_days"))
@router.channel_post(Command("digest_days"))
async def cmd_digest_days(
    message: Message, command: CommandObject, bot: Bot, session: AsyncSession
) -> None:
    """Set this chat's delivery weekdays."""
    if not is_managed_chat(message):
        await message.answer(texts.NOT_GROUP)
        return
    if not await is_authorized_operator(bot, message):
        await message.answer(texts.NOT_CHAT_ADMIN, parse_mode=ParseMode.HTML)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(texts.DIGEST_DAYS_USAGE, parse_mode=ParseMode.HTML)
        return
    try:
        days = normalize_weekdays(raw.replace(",", " ").split())
    except ValueError:
        await message.answer(texts.DIGEST_DAYS_BAD, parse_mode=ParseMode.HTML)
        return

    if not await repo.set_digest_days(session, message.chat.id, days):
        await message.answer(texts.GROUP_UNKNOWN, parse_mode=ParseMode.HTML)
        return

    log.info("group.days_changed", chat_id=message.chat.id, days=days)
    await message.answer(
        texts.DIGEST_DAYS_OK.format(days=html.escape(format_weekdays(days))),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("timezone"))
@router.channel_post(Command("timezone"))
async def cmd_timezone(
    message: Message, command: CommandObject, bot: Bot, session: AsyncSession
) -> None:
    """Set this chat's timezone (IANA name, e.g. ``Europe/Moscow``)."""
    if not is_managed_chat(message):
        await message.answer(texts.NOT_GROUP)
        return
    if not await is_authorized_operator(bot, message):
        await message.answer(texts.NOT_CHAT_ADMIN, parse_mode=ParseMode.HTML)
        return

    tz = (command.args or "").strip()
    if not tz:
        await message.answer(texts.TIMEZONE_USAGE, parse_mode=ParseMode.HTML)
        return
    try:
        zoneinfo.ZoneInfo(tz)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        await message.answer(texts.TIMEZONE_BAD, parse_mode=ParseMode.HTML)
        return

    if not await repo.set_timezone(session, message.chat.id, tz):
        await message.answer(texts.GROUP_UNKNOWN, parse_mode=ParseMode.HTML)
        return

    log.info("group.timezone_changed", chat_id=message.chat.id, tz=tz)
    await message.answer(texts.TIMEZONE_OK.format(tz=html.escape(tz)), parse_mode=ParseMode.HTML)
