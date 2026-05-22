"""Deduplication: batch URL collapse and fuzzy title matching."""

from __future__ import annotations

import uuid

from app.domain.schemas import RawItem
from app.services.dedup import dedup_within_batch, find_title_duplicate


def _item(title: str, url: str) -> RawItem:
    return RawItem(title=title, url=url, source="test")


def test_dedup_within_batch_collapses_same_url() -> None:
    items = [
        _item("Llama 4 released", "https://meta.ai/llama4"),
        _item("Llama 4 is here", "https://www.meta.ai/llama4/"),  # same after norm
        _item("Different story", "https://other.com/x"),
    ]
    unique = dedup_within_batch(items)
    assert len(unique) == 2
    assert unique[0].title == "Llama 4 released"  # first occurrence wins


def test_dedup_within_batch_preserves_distinct() -> None:
    items = [_item("A", "https://a.com"), _item("B", "https://b.com")]
    assert len(dedup_within_batch(items)) == 2


def test_find_title_duplicate_matches_reordered_words() -> None:
    known = [(uuid.uuid4(), "Meta releases Llama 4 open weights")]
    twin = find_title_duplicate("Llama 4 open weights released by Meta", known)
    assert twin == known[0][0]


def test_find_title_duplicate_no_false_positive() -> None:
    known = [(uuid.uuid4(), "OpenAI ships a new image model")]
    assert find_title_duplicate("Anthropic publishes a safety paper", known) is None


def test_find_title_duplicate_empty_inputs() -> None:
    assert find_title_duplicate("", []) is None
    assert find_title_duplicate("anything", []) is None
