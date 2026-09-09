"""Scoring status-decision policy.

The flow is fully automatic — there is no moderation step:

* ``score < threshold``     -> REJECTED
* ``threshold .. 8``        -> APPROVED  (delivered on the chat's schedule)
* ``9 .. 10``               -> BREAKING  (pushed immediately, off-schedule)

``BREAKING`` only exists while ``BREAKING_ENABLED`` is on. Under the shipped
twice-weekly schedule it is off and every accepted item is ``APPROVED``.
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


@pytest.fixture
def _breaking_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "breaking_enabled", True)


def test_below_threshold_is_rejected() -> None:
    assert decide_status(_verdict(6)) is NewsStatus.REJECTED


def test_scores_up_to_8_are_scheduled_automatically() -> None:
    # No moderation: threshold..8 is approved straight away.
    assert decide_status(_verdict(7)) is NewsStatus.APPROVED
    assert decide_status(_verdict(8)) is NewsStatus.APPROVED


@pytest.mark.usefixtures("_breaking_on")
def test_high_score_becomes_breaking_when_enabled() -> None:
    # Score > 8 bypasses the schedule entirely — but only if urgent pushes are on.
    assert decide_status(_verdict(9)) is NewsStatus.BREAKING
    assert decide_status(_verdict(10)) is NewsStatus.BREAKING


def test_high_score_waits_for_the_schedule_by_default() -> None:
    # Urgent pushes ship disabled: a 10/10 item just leads the next digest.
    assert get_settings().breaking_enabled is False
    assert decide_status(_verdict(9)) is NewsStatus.APPROVED
    assert decide_status(_verdict(10)) is NewsStatus.APPROVED
