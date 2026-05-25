"""Broadcaster behaviour that does not require Telegram."""

from __future__ import annotations

import uuid

import pytest
from app.services.broadcaster import Broadcaster, ChatDestination
from app.services.digest import DigestCard

pytestmark = pytest.mark.asyncio


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.photos: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> None:
        self.messages.append(kwargs)

    async def send_photo(self, **kwargs: object) -> None:
        self.photos.append(kwargs)


async def test_send_one_passes_message_thread_id() -> None:
    bot = FakeBot()
    broadcaster = Broadcaster(bot, messages_per_second=1000)

    await broadcaster.send_one(-100, "hello", message_thread_id=42)

    assert bot.messages == [
        {
            "chat_id": -100,
            "message_thread_id": 42,
            "parse_mode": "MarkdownV2",
            "text": "hello",
        }
    ]


async def test_deliver_digest_uses_topic_for_header_and_cards() -> None:
    bot = FakeBot()
    broadcaster = Broadcaster(bot, messages_per_second=1000)
    card = DigestCard(item_id=uuid.uuid4(), text="card", image_url="https://example.com/a.png")

    result = await broadcaster.deliver_digest("header", [card], [ChatDestination(-100, 777)])

    assert result.sent == [-100]
    assert bot.messages[0]["message_thread_id"] == 777
    assert bot.photos[0]["message_thread_id"] == 777
