"""URL normalisation — the exact-duplicate guard."""

from __future__ import annotations

import pytest
from app.utils.url import domain_of, normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://openai.com/blog/", "https://openai.com/blog"),
        ("http://www.OpenAI.com/Blog", "https://openai.com/Blog"),
        (
            "https://example.com/post?utm_source=hn&utm_medium=feed",
            "https://example.com/post",
        ),
        (
            "https://example.com/post?id=42&ref=twitter",
            "https://example.com/post?id=42",
        ),
        ("https://example.com/p#section", "https://example.com/p"),
        ("example.com/x", "https://example.com/x"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_normalize_url_is_idempotent() -> None:
    once = normalize_url("http://www.example.com/a/?utm_source=x#frag")
    assert normalize_url(once) == once


def test_query_order_does_not_matter() -> None:
    assert normalize_url("https://x.com/p?b=2&a=1") == normalize_url("https://x.com/p?a=1&b=2")


def test_empty_url() -> None:
    assert normalize_url("") == ""


def test_domain_of() -> None:
    assert domain_of("https://www.huggingface.co/papers/123") == "huggingface.co"
