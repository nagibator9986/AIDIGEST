"""Text utilities: MarkdownV2 escaping, relevance filter, truncation."""

from __future__ import annotations

from app.utils.text import escape_markdown_v2, is_ai_relevant, truncate


def test_escape_markdown_v2_escapes_specials() -> None:
    escaped = escape_markdown_v2("a-b.c (x) [y]!")
    for char in "-.()[]!":
        assert f"\\{char}" in escaped


def test_escape_markdown_v2_plain_text_unchanged() -> None:
    assert escape_markdown_v2("simple text") == "simple text"


def test_is_ai_relevant_positive() -> None:
    assert is_ai_relevant("New LLM released", "details about the model")
    assert is_ai_relevant("A guide to RAG pipelines")
    assert is_ai_relevant("Deep learning at scale")


def test_is_ai_relevant_negative() -> None:
    assert not is_ai_relevant("A new JavaScript date library")
    assert not is_ai_relevant("Quarterly sales results")


def test_is_ai_relevant_avoids_substring_false_positive() -> None:
    # "email" contains "ai" but must not match as a whole word.
    assert not is_ai_relevant("Best email clients of 2026")


def test_truncate_short_text_unchanged() -> None:
    assert truncate("hello", 100) == "hello"


def test_truncate_long_text_adds_suffix() -> None:
    result = truncate("word " * 50, 40)
    assert len(result) <= 40
    assert result.endswith("…")
