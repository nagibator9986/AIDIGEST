"""Deduplication — two layers of defence against the same story landing twice.

1. **URL identity** — normalised-URL equality (cheap, exact).
2. **Title similarity** — fuzzy match against recently seen titles, so the
   same release reported by HN *and* an RSS feed collapses into one item.
"""

from __future__ import annotations

import uuid
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover -- exercised indirectly in this environment
    fuzz = None  # type: ignore[assignment]

from app.domain.schemas import RawItem

# token_set_ratio >= this => treat as the same story.
TITLE_SIMILARITY_THRESHOLD = 88


def _token_set_ratio(left: str, right: str) -> float:
    """Best-effort token-set similarity.

    ``rapidfuzz`` is preferred when installed. If it is unavailable, fall back
    to a deterministic standard-library approximation based on sorted unique
    tokens. That keeps deduplication functional in constrained environments
    instead of crashing the ingestion pipeline at import time.
    """
    if fuzz is not None:
        return float(fuzz.token_set_ratio(left, right))
    left_tokens = " ".join(sorted(set(left.split())))
    right_tokens = " ".join(sorted(set(right.split())))
    if not left_tokens or not right_tokens:
        return 0.0
    return SequenceMatcher(None, left_tokens, right_tokens).ratio() * 100.0


def dedup_within_batch(items: list[RawItem]) -> list[RawItem]:
    """Collapse exact normalised-URL duplicates inside a single ingestion batch.

    The first occurrence wins; ties keep collector registry order.
    """
    seen: set[str] = set()
    unique: list[RawItem] = []
    for item in items:
        key = item.normalized_url
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def find_title_duplicate(title: str, known: list[tuple[uuid.UUID, str]]) -> uuid.UUID | None:
    """Return the id of an existing item whose title matches *title*, if any.

    Uses ``token_set_ratio`` so word-order and length differences (e.g.
    "Llama 4 released" vs "Meta releases Llama 4") still match.
    """
    needle = title.lower().strip()
    if not needle:
        return None
    best_id: uuid.UUID | None = None
    best_score: float = TITLE_SIMILARITY_THRESHOLD
    for item_id, existing_title in known:
        score = _token_set_ratio(needle, existing_title.lower().strip())
        if score >= best_score:
            best_score = score
            best_id = item_id
    return best_id
