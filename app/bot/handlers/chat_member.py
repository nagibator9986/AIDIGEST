"""Handle the bot being added to / removed from chats.

Telegram delivers a ``my_chat_member`` update whenever the bot's own
membership changes. We use it to keep the ``groups`` table in sync without
ever requiring the bot to be a chat administrator.
"""

from __future__ import annotations

import html

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.types import ChatMemberUpdated

from app.bot import texts
from app.config import get_settings
from app.db import repositories as repo
from app.db.base import AsyncSession
from app.logging import get_logger

router = Router(name="chat_member")
log = get_logger(__name__)

_PRESENT = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR}
_GONE = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.RESTRICTED}


@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated, bot: Bot, session: AsyncSession) -> None:
    """React to the bot's membership changing in a chat."""
    chat = event.chat
    new_status = event.new_chat_member.status

    # Direct messages are not "groups" — ignore membership noise there.
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        return

    if new_status in _PRESENT:
        settings = get_settings()
        _group, created = await repo.upsert_group(
            session,
            chat_id=chat.id,
            title=chat.title or chat.full_name or str(chat.id),
            chat_type=chat.type,
            added_by=event.from_user.id if event.from_user else None,
            default_time=settings.digest_time,
            default_tz=settings.timezone,
        )
        log.info("group.joined", chat_id=chat.id, title=chat.title, created=created)
        try:
            await bot.send_message(
                chat.id,
                texts.WELCOME_GROUP.format(
                    time=html.escape(settings.digest_time),
                    tz=html.escape(settings.timezone),
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            log.warning("group.welcome_failed", chat_id=chat.id, error=str(exc))

    elif new_status in _GONE:
        await repo.deactivate_group(session, chat.id)
        log.info("group.left", chat_id=chat.id, status=new_status)
