"""Inline keyboards and their callback-data contracts."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.schedule import WEEKDAY_LABELS_SHORT, canonical_weekdays
from app.config import ALL_DIGEST_WEEKDAYS


class SettingsCallback(CallbackData, prefix="cfg"):
    """Callback payload for the in-chat digest settings panel."""

    action: str  # freq1 | freq2 | freq3 | toggle_day | pause | resume | refresh
    value: str = ""


# Frequency presets offered by the settings panel buttons.
FREQUENCY_PRESETS: dict[str, list[str]] = {
    "freq1": ["09:00"],
    "freq2": ["09:00", "19:00"],
    "freq3": ["09:00", "14:00", "20:00"],
}


def settings_keyboard(*, paused: bool, days: list[int] | None) -> InlineKeyboardMarkup:
    """Inline panel: presets, weekday toggles, pause/resume toggle and refresh."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="1 / день", callback_data=SettingsCallback(action="freq1", value="").pack()
        ),
        InlineKeyboardButton(
            text="2 / день", callback_data=SettingsCallback(action="freq2", value="").pack()
        ),
        InlineKeyboardButton(
            text="3 / день", callback_data=SettingsCallback(action="freq3", value="").pack()
        ),
    )
    selected = set(canonical_weekdays(days))
    weekday_buttons = [
        InlineKeyboardButton(
            text=f"{'✅' if day in selected else '▫️'} {WEEKDAY_LABELS_SHORT[day]}",
            callback_data=SettingsCallback(action="toggle_day", value=str(day)).pack(),
        )
        for day in ALL_DIGEST_WEEKDAYS
    ]
    builder.row(*weekday_buttons[:4])
    builder.row(*weekday_buttons[4:])
    if paused:
        builder.row(
            InlineKeyboardButton(
                text="▶️ Возобновить",
                callback_data=SettingsCallback(action="resume", value="").pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="⏸ Поставить на паузу",
                callback_data=SettingsCallback(action="pause", value="").pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔄 Обновить", callback_data=SettingsCallback(action="refresh", value="").pack()
        )
    )
    return builder.as_markup()
