"""Reusable aiogram filters and authorisation helpers."""

from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

_ADMIN_STATUSES = {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}


class IsBotAdmin(BaseFilter):
    """Pass only for users listed in ``ADMIN_IDS`` — bot-wide operators."""

    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        return user is not None and user.id in get_settings().admin_ids


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """True if *user_id* is an owner/administrator of *chat_id*.

    Failures (e.g. the bot cannot see the member list) deny by default.
    """
    # Bot-wide operators are always treated as chat admins.
    if user_id in get_settings().admin_ids:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as exc:
        log.debug("filters.chat_admin_check_failed", chat_id=chat_id, error=str(exc))
        return False
    return member.status in _ADMIN_STATUSES


def is_managed_chat(message: Message) -> bool:
    """True for any chat the bot delivers digests to — group, supergroup or channel."""
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL)


async def is_authorized_operator(bot: Bot, message: Message) -> bool:
    """True if the sender may run management commands in *message*'s chat.

    A ``channel_post`` can only be authored by a channel administrator, so it
    is authorised unconditionally. In groups we fall back to the chat-admin
    check against the posting user.
    """
    if message.chat.type == ChatType.CHANNEL:
        return True
    user = message.from_user
    if user is None:
        return False
    return await is_chat_admin(bot, message.chat.id, user.id)
