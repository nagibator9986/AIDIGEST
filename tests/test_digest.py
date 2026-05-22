"""Digest rendering — MarkdownV2 cards, header and caption-length safety."""

from __future__ import annotations

from datetime import date

from app.db.models import NewsItem
from app.domain.enums import NewsCategory
from app.services.digest import render_breaking_news, render_card, render_header
from app.utils.images import looks_like_image

# Telegram hard limit for a photo caption.
_CAPTION_LIMIT = 1024


def _news(**overrides: object) -> NewsItem:
    defaults: dict[str, object] = {
        "title": "Meta releases Llama 4",
        "source_url": "https://meta.ai/llama-4",
        "normalized_url": "https://meta.ai/llama-4",
        "source": "rss",
        "category": NewsCategory.MODEL_RELEASE,
        "score": 8,
        "summary_ru": "Meta выпустила Llama 4 с открытыми весами.",
        "utility_ru": "Можно запускать локально без облака.",
        "key_points": None,
        "extra_sources": [],
    }
    defaults.update(overrides)
    return NewsItem(**defaults)


def test_render_header_empty() -> None:
    header = render_header(date(2026, 5, 22), 0)
    assert "AI Insight Digest" in header
    assert "22 мая 2026" in header


def test_render_header_with_count() -> None:
    header = render_header(date(2026, 5, 22), 5)
    assert "топ\\-5" in header


def test_render_card_has_score_and_link() -> None:
    card = render_card(1, _news(score=9))
    assert "9/10" in card
    assert "Читать оригинал" in card


def test_render_card_escapes_special_characters() -> None:
    card = render_card(1, _news(title="GPT-5 (preview) is here!"))
    assert "\\-" in card and "\\(" in card and "\\!" in card


def test_render_card_shows_key_points() -> None:
    card = render_card(1, _news(key_points=["Контекст: 1M токенов", "Бесплатно"]))
    assert "Контекст: 1M токенов" in card


def test_render_card_fits_telegram_caption_limit() -> None:
    long = "Очень длинное предложение про искусственный интеллект. " * 30
    card = render_card(
        1,
        _news(
            title="Длинный заголовок новости " * 8,
            summary_ru=long,
            utility_ru=long,
            key_points=[long, long, long],
        ),
    )
    assert len(card) <= _CAPTION_LIMIT


def test_render_breaking_news_fits_caption_limit() -> None:
    long = "Срочная новость про взлом и новую модель. " * 30
    caption = render_breaking_news(
        _news(title="Срочно " * 20, summary_ru=long, utility_ru=long, key_points=[long, long])
    )
    assert "Срочная" in caption
    assert len(caption) <= _CAPTION_LIMIT


def test_looks_like_image() -> None:
    assert looks_like_image("https://cdn.example.com/banner.jpg")
    assert looks_like_image("https://cdn.example.com/og/article-123")  # extension-less
    assert not looks_like_image("https://example.com/page.html")
    assert not looks_like_image(None)
    assert not looks_like_image("")
