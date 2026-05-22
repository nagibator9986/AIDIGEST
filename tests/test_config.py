"""Configuration parsing and validation."""

from __future__ import annotations

import pytest
from app.config import Settings, get_settings, normalize_schedule, normalize_weekdays, parse_hhmm


@pytest.mark.parametrize(
    ("value", "hour", "minute"),
    [("09:00", 9, 0), ("23:59", 23, 59), ("0:5", 0, 5)],
)
def test_parse_hhmm_valid(value: str, hour: int, minute: int) -> None:
    parsed = parse_hhmm(value)
    assert (parsed.hour, parsed.minute) == (hour, minute)


@pytest.mark.parametrize("value", ["24:00", "12:60", "abc", "12", "12:30:00"])
def test_parse_hhmm_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_hhmm(value)


def test_admin_ids_parsed_from_csv() -> None:
    # conftest sets ADMIN_IDS=111,222
    assert get_settings().admin_ids == [111, 222]


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_producthunt_token_is_none(blank: str) -> None:
    # An empty `PRODUCTHUNT_TOKEN=` env var must disable the collector,
    # not become an empty-string token.
    assert Settings(producthunt_token=blank).producthunt_token is None


def test_real_producthunt_token_is_kept() -> None:
    settings = Settings(producthunt_token="ph_secret_123")
    assert settings.producthunt_token is not None
    assert settings.producthunt_token.get_secret_value() == "ph_secret_123"


def test_normalize_schedule_sorts_and_dedups() -> None:
    assert normalize_schedule(["18:00", "9:00", "09:00"]) == ["09:00", "18:00"]


@pytest.mark.parametrize("bad", [["25:00"], ["nope"], []])
def test_normalize_schedule_rejects_invalid(bad: list[str]) -> None:
    with pytest.raises(ValueError):
        normalize_schedule(bad)


def test_normalize_schedule_caps_count() -> None:
    with pytest.raises(ValueError):
        normalize_schedule([f"{h:02d}:00" for h in range(9)])  # 9 > MAX (8)


def test_normalize_weekdays_accepts_russian_labels_and_sorts() -> None:
    assert normalize_weekdays(["пт", "пн", "ср"]) == [1, 3, 5]


def test_normalize_weekdays_expands_all() -> None:
    assert normalize_weekdays(["все"]) == [1, 2, 3, 4, 5, 6, 7]


@pytest.mark.parametrize("bad", [[""], ["foo"], ["8"], []])
def test_normalize_weekdays_rejects_invalid(bad: list[str]) -> None:
    with pytest.raises(ValueError):
        normalize_weekdays(bad)
