"""Broadcaster — stage 4b: rate-limit-aware delivery to many chats.

Telegram caps bulk delivery at ~30 messages/second across distinct chats. The
broadcaster paces sends below that ceiling and treats every Telegram failure
mode explicitly:

* ``TelegramRetryAfter``     — honour the server's back-off, then retry once.
* ``TelegramForbiddenError`` — the bot was kicked/blocked: report it *blocked*
  so the caller can deactivate the chat.
* ``TelegramBadRequest`` on a photo — the image URL is unusable: silently fall
  back to a plain text message so the news still gets through.
* other API errors — reported as *failed*, never fatal to the batch.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypeAlias

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.logging import get_logger
from app.services.digest import DigestCard

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChatDestination:
    """A Telegram chat, optionally narrowed to a forum topic."""

    chat_id: int
    message_thread_id: int | None = None


DestinationInput: TypeAlias = int | ChatDestination


@dataclass(slots=True)
class BroadcastResult:
    """Per-chat outcome of a broadcast."""

    sent: list[int] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)
    blocked: list[int] = field(default_factory=list)  # bot kicked/blocked

    @property
    def total(self) -> int:
        return len(self.sent) + len(self.failed) + len(self.blocked)


class Broadcaster:
    """Delivers messages — text or photo — to many chats within rate limits."""

    def __init__(self, bot: Bot, *, messages_per_second: float = 25.0) -> None:
        self._bot = bot
        self._delay = 1.0 / messages_per_second

    @staticmethod
    def _destination(value: DestinationInput) -> ChatDestination:
        if isinstance(value, ChatDestination):
            return value
        return ChatDestination(chat_id=value)

    async def _deliver_message(
        self, destination: ChatDestination, text: str, image_url: str | None
    ) -> None:
        """Send one message — a photo with caption, or plain text."""
        kwargs = {
            "chat_id": destination.chat_id,
            "parse_mode": ParseMode.MARKDOWN_V2,
        }
        if destination.message_thread_id is not None:
            kwargs["message_thread_id"] = destination.message_thread_id
        if image_url:
            try:
                await self._bot.send_photo(
                    photo=image_url,
                    caption=text,
                    **kwargs,
                )
                return
            except (TelegramRetryAfter, TelegramForbiddenError):
                raise
            except TelegramBadRequest as exc:
                # Unusable image (Telegram could not fetch it) — degrade to text.
                log.info(
                    "broadcast.photo_fallback", chat_id=destination.chat_id, error=str(exc)
                )
        await self._bot.send_message(text=text, **kwargs)

    async def _send(
        self, destination: ChatDestination, text: str, image_url: str | None
    ) -> None:
        """Send one message, honouring a single ``RetryAfter`` back-off."""
        try:
            await self._deliver_message(destination, text, image_url)
        except TelegramRetryAfter as exc:
            log.warning(
                "broadcast.retry_after",
                chat_id=destination.chat_id,
                seconds=exc.retry_after,
            )
            await asyncio.sleep(exc.retry_after + 1)
            await self._deliver_message(destination, text, image_url)

    async def send_one(
        self,
        chat_id: int,
        text: str,
        image_url: str | None = None,
        *,
        message_thread_id: int | None = None,
    ) -> None:
        """Send a single message (optionally a photo) to one chat."""
        await self._send(ChatDestination(chat_id, message_thread_id), text, image_url)

    async def broadcast(
        self, text: str, chat_ids: Sequence[DestinationInput], *, image_url: str | None = None
    ) -> BroadcastResult:
        """Deliver one message (optionally a photo) to every chat."""
        result = BroadcastResult()
        for value in chat_ids:
            destination = self._destination(value)
            try:
                await self._send(destination, text, image_url)
                result.sent.append(destination.chat_id)
            except TelegramForbiddenError:
                result.blocked.append(destination.chat_id)
                log.info("broadcast.blocked", chat_id=destination.chat_id)
            except Exception as exc:
                result.failed[destination.chat_id] = str(exc)
                log.warning("broadcast.failed", chat_id=destination.chat_id, error=str(exc))
            await asyncio.sleep(self._delay)
        return result

    async def deliver_digest(
        self, header: str, cards: list[DigestCard], chat_ids: Sequence[DestinationInput]
    ) -> BroadcastResult:
        """Deliver a digest — a header message then one card per item."""
        result = BroadcastResult()
        for value in chat_ids:
            destination = self._destination(value)
            try:
                await self._send(destination, header, None)
                for card in cards:
                    await asyncio.sleep(self._delay)
                    await self._send(destination, card.text, card.image_url)
                result.sent.append(destination.chat_id)
            except TelegramForbiddenError:
                result.blocked.append(destination.chat_id)
                log.info("broadcast.blocked", chat_id=destination.chat_id)
            except Exception as exc:
                result.failed[destination.chat_id] = str(exc)
                log.warning("broadcast.failed", chat_id=destination.chat_id, error=str(exc))
            await asyncio.sleep(self._delay)

        log.info(
            "broadcast.digest_done",
            chats=len(chat_ids),
            cards=len(cards),
            sent=len(result.sent),
            failed=len(result.failed),
            blocked=len(result.blocked),
        )
        return result
