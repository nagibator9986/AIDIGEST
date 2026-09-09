"""Delivery scheduling — the per-chat, multi-slot "which slots are due" logic."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from app.db.models import Group
from app.services import delivery


def _group(**overrides: object) -> Group:
    defaults: dict[str, object] = {
        "id": -100,
        "digest_times": ["09:00"],
        "digest_days": [1, 5],  # the shipped default: Mon + Fri
        "timezone": "UTC",
        "last_digest_on": None,
        "sent_slots_today": [],
        "digest_paused": False,
    }
    defaults.update(overrides)
    return Group(**defaults)


def _freeze(monkeypatch: pytest.MonkeyPatch, hh: int, mm: int, day: int = 22) -> None:
    """Pin :func:`delivery.now_in` to a fixed local time.

    The default day, 2026-05-22, is a Friday — one of the two weekdays the
    shipped schedule delivers on.
    """
    fixed = datetime(2026, 5, day, hh, mm)
    monkeypatch.setattr(delivery, "now_in", lambda _tz: fixed)


def test_no_slot_due_before_first_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, 8, 59)
    _today, due = delivery._due_slots(_group(digest_times=["09:00", "18:00"]))
    assert due == []


def test_slot_due_at_its_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, 9, 0)
    today, due = delivery._due_slots(_group())
    assert due == ["09:00"]
    assert today == date(2026, 5, 22)


def test_slot_not_due_on_disabled_weekday(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, 9, 0)
    _today, due = delivery._due_slots(_group(digest_days=[1, 3]))
    assert due == []


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (18, ["09:00"]),  # Mon — delivery day
        (19, []),  # Tue
        (20, []),  # Wed
        (21, []),  # Thu
        (22, ["09:00"]),  # Fri — delivery day
        (23, []),  # Sat
        (24, []),  # Sun
    ],
)
def test_default_schedule_delivers_only_monday_and_friday(
    monkeypatch: pytest.MonkeyPatch, day: int, expected: list[str]
) -> None:
    """The whole week at 09:00: exactly two mornings produce a digest."""
    _freeze(monkeypatch, 9, 0, day=day)
    _today, due = delivery._due_slots(_group())
    assert due == expected


def test_slot_still_due_after_a_missed_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, 11, 30)
    _today, due = delivery._due_slots(_group())
    assert due == ["09:00"]


def test_already_sent_slot_is_not_due(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, 12, 0)
    group = _group(last_digest_on=date(2026, 5, 22), sent_slots_today=["09:00"])
    _today, due = delivery._due_slots(group)
    assert due == []


def test_multiple_slots_only_passed_ones_are_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch, 12, 0)
    group = _group(digest_times=["09:00", "14:00", "20:00"])
    _today, due = delivery._due_slots(group)
    assert due == ["09:00"]


def test_catch_up_returns_all_passed_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, 21, 0)
    group = _group(digest_times=["09:00", "14:00", "20:00"])
    _today, due = delivery._due_slots(group)
    assert due == ["09:00", "14:00", "20:00"]


def test_sent_slots_reset_on_a_new_delivery_day(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, 9, 0, day=25)  # the following Monday
    # sent_slots_today refers to Friday the 22nd; on Monday it must not apply.
    group = _group(last_digest_on=date(2026, 5, 22), sent_slots_today=["09:00"])
    today, due = delivery._due_slots(group)
    assert today == date(2026, 5, 25)
    assert due == ["09:00"]
