"""Digest service — stage 4a: select the best items and render the cards.

A digest is built **on demand** for each delivery: the top approved items not
yet posted are selected, each rendered as a *card* (a short MarkdownV2 caption
plus an optional preview image) and marked ``POSTED``. Delivering card-by-card
lets every news item arrive with its own picture instead of a wall of text.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

import httpx

from app.collectors.base import make_http_client
from app.config import get_settings
from app.db import repositories as repo
from app.db.base import AsyncSession, session_scope
from app.db.models import NewsItem
from app.domain.enums import NewsCategory
from app.logging import get_logger
from app.utils.images import extract_image_url, looks_like_image
from app.utils.text import escape_markdown_v2, truncate

log = get_logger(__name__)

# Telegram photo captions are capped at 1024 characters — card text stays well
# under that even after MarkdownV2 escaping.
_EMPTY_TEXT = (
    "Сегодня значимых новостей не нашлось — ИИ-редактор отсеял весь "
    "информационный шум. Это тоже результат: ничего важного вы не пропустили."
)
_MONTHS_RU = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


@dataclass(slots=True)
class DigestCard:
    """One news item rendered for delivery — caption text + optional image."""

    item_id: uuid.UUID
    text: str
    image_url: str | None = None


@dataclass(slots=True)
class DigestContent:
    """A built digest ready to broadcast: a header plus one card per item."""

    digest_date: date
    header: str
    cards: list[DigestCard] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.cards

    @property
    def item_ids(self) -> list[uuid.UUID]:
        return [card.item_id for card in self.cards]


def _escape_url(url: str) -> str:
    """Escape a URL for use inside a MarkdownV2 ``(...)`` link target."""
    return url.replace("\\", "\\\\").replace(")", "\\)")


def _render_date(on_date: date) -> str:
    return f"{on_date.day} {_MONTHS_RU[on_date.month]} {on_date.year}"


def render_header(on_date: date, count: int) -> str:
    """Render the short digest header message (MarkdownV2)."""
    if count == 0:
        return (
            "🤖 *AI Insight Digest*\n"
            f"📅 {escape_markdown_v2(_render_date(on_date))}\n\n" + escape_markdown_v2(_EMPTY_TEXT)
        )
    return (
        "🤖 *AI Insight Digest*\n"
        f"📅 {escape_markdown_v2(_render_date(on_date))} · "
        f"топ\\-{count} за период\n"
        "_Самое полезное по AI: инструменты, курсы и сценарии применения\\._"
    )


def render_card(index: int, item: NewsItem) -> str:
    """Render one news card as a compact MarkdownV2 photo caption."""
    category = NewsCategory(item.category) if item.category else NewsCategory.OTHER
    title = escape_markdown_v2(truncate(item.title, 120))
    summary = escape_markdown_v2(truncate(item.summary_ru or "", 240))
    utility = escape_markdown_v2(truncate(item.utility_ru or "", 160))

    lines = [
        f"{category.emoji} *{index}\\. {title}*",
        f"⭐️ {item.score or 0}/10",
        "",
        summary,
    ]
    for point in (item.key_points or [])[:2]:
        lines.append(f"  • {escape_markdown_v2(truncate(point, 85))}")
    lines.append(f"\n💡 _Польза:_ {utility}")
    lines.append(f"🔗 [Читать оригинал]({_escape_url(item.source_url)})")
    return "\n".join(lines)


def render_breaking_news(item: NewsItem) -> str:
    """Render one urgent, out-of-band news alert (MarkdownV2 photo caption)."""
    category = NewsCategory(item.category) if item.category else NewsCategory.OTHER
    title = escape_markdown_v2(truncate(item.title, 120))
    summary = escape_markdown_v2(truncate(item.summary_ru or "", 260))
    utility = escape_markdown_v2(truncate(item.utility_ru or "", 160))

    lines = [
        "🚨 *Срочная AI\\-новость*",
        f"{category.emoji} *{title}*",
        f"⭐️ {item.score or 0}/10 · вне расписания",
        "",
        summary,
    ]
    for point in (item.key_points or [])[:2]:
        lines.append(f"  • {escape_markdown_v2(truncate(point, 85))}")
    lines.append(f"\n💡 _Польза:_ {utility}")
    lines.append(f"🔗 [Читать оригинал]({_escape_url(item.source_url)})")
    return "\n".join(lines)


async def ensure_item_image(client: httpx.AsyncClient, item: NewsItem) -> None:
    """Populate ``item.image_url`` from the article's og:image if still unset.

    A non-null empty string records "already looked, found nothing" so the
    page is not refetched on every later digest.
    """
    if item.image_url is not None:
        return
    found = await extract_image_url(client, item.source_url)
    item.image_url = found if (found and looks_like_image(found)) else ""


async def build_digest(session: AsyncSession, on_date: date) -> DigestContent:
    """Select top approved-and-unposted items, render cards, mark them POSTED.

    Runs inside the caller's transaction. Preview images are fetched lazily for
    just the selected items and cached on the row.
    """
    settings = get_settings()
    items = await repo.select_digest_items(
        session,
        lookback_days=settings.lookback_days,
        threshold=settings.score_threshold,
        limit=settings.digest_size,
    )
    if not items:
        return DigestContent(digest_date=on_date, header=render_header(on_date, 0))

    async with make_http_client() as client:
        for item in items:
            await ensure_item_image(client, item)

    cards = [
        DigestCard(
            item_id=item.id,
            text=render_card(index, item),
            image_url=item.image_url or None,
        )
        for index, item in enumerate(items, start=1)
    ]
    await repo.mark_posted(session, [item.id for item in items])
    log.info("digest.built", date=on_date.isoformat(), items=len(cards))
    return DigestContent(
        digest_date=on_date, header=render_header(on_date, len(cards)), cards=cards
    )


async def build_digest_content(on_date: date) -> DigestContent:
    """Build the digest for *on_date* in its own transaction."""
    async with session_scope() as session:
        return await build_digest(session, on_date)
