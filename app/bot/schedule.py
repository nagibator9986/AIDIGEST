"""Small helpers for rendering and validating chat delivery schedules."""

from __future__ import annotations

from app.config import ALL_DIGEST_WEEKDAYS, normalize_weekdays

WEEKDAY_LABELS_SHORT = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}


def canonical_weekdays(days: list[int] | None) -> list[int]:
    """Return ordered ISO weekdays, defaulting to every day when unset."""
    return normalize_weekdays(list(days or ALL_DIGEST_WEEKDAYS))


def format_weekdays(days: list[int] | None) -> str:
    """Human-readable weekday list for the settings panel."""
    canonical = canonical_weekdays(days)
    if canonical == ALL_DIGEST_WEEKDAYS:
        return "каждый день"
    return ", ".join(WEEKDAY_LABELS_SHORT[day] for day in canonical)
