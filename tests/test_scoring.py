"""Scoring status-decision policy.

The flow is fully automatic — there is no moderation step:

* ``score < threshold``     -> REJECTED
* ``threshold .. 8``        -> APPROVED  (delivered on the chat's schedule)
* ``9 .. 10``               -> BREAKING  (pushed immediately, off-schedule)
"""

from __future__ import annotations

import pytest
from app.config import get_settings
from app.domain.enums import NewsCategory, NewsStatus
from app.domain.schemas import GeminiVerdict
from app.services.scoring import decide_status


def _verdict(score: int) -> GeminiVerdict:
    return GeminiVerdict(
        reasoning="test",
        score=score,
        category=NewsCategory.TOOL,
        is_hype=False,
        summary_ru="сводка",
        key_points_ru=["факт 1", "факт 2"],
        utility_ru="польза",
    )


@pytest.fixture(autouse=True)
def _threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "score_threshold", 7)


def test_below_threshold_is_rejected() -> None:
    assert decide_status(_verdict(6)) is NewsStatus.REJECTED


def test_scores_up_to_8_are_scheduled_automatically() -> None:
    # No moderation: threshold..8 is approved straight away.
    assert decide_status(_verdict(7)) is NewsStatus.APPROVED
    assert decide_status(_verdict(8)) is NewsStatus.APPROVED


def test_high_score_becomes_breaking() -> None:
    # Score > 8 bypasses the schedule entirely.
    assert decide_status(_verdict(9)) is NewsStatus.BREAKING
    assert decide_status(_verdict(10)) is NewsStatus.BREAKING
