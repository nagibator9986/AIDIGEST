"""Composition of the in-chat settings panel (message text + inline keyboard)."""

from __future__ import annotations

import html

from aiogram.types import InlineKeyboardMarkup

from app.bot import texts
from app.bot.keyboards import settings_keyboard
from app.bot.schedule import format_weekdays
from app.db.models import Group


def plural_times(n: int) -> str:
    """Russian-pluralised frequency label, e.g. ``"2 раза в день"``."""
    if n % 10 == 1 and n % 100 != 11:
        word = "раз"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "раза"
    else:
        word = "раз"
    return f"{n} {word} в день"


def render_settings_panel(group: Group) -> tuple[str, InlineKeyboardMarkup]:
    """Return the ``(text, keyboard)`` for *group*'s settings panel."""
    times = list(group.digest_times or [])
    status = texts.SETTINGS_STATUS_PAUSED if group.digest_paused else texts.SETTINGS_STATUS_ACTIVE
    text = texts.SETTINGS_PANEL.format(
        times=html.escape(", ".join(times)) if times else "—",
        freq=plural_times(len(times)) if times else "—",
        days=html.escape(format_weekdays(group.digest_days)),
        tz=html.escape(group.timezone),
        status_line=status,
    )
    return text, settings_keyboard(paused=group.digest_paused, days=group.digest_days)
