"""Settings-panel callbacks — frequency presets and pause/resume buttons.

The ``/settings`` command itself lives in :mod:`app.bot.handlers.commands`;
this router only handles the inline-button interactions on that panel.
"""

from __future__ import annotations

import contextlib

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.filters import is_chat_admin
from app.bot.keyboards import FREQUENCY_PRESETS, SettingsCallback
from app.bot.panels import plural_times, render_settings_panel
from app.bot.schedule import canonical_weekdays, format_weekdays
from app.db import repositories as repo
from app.db.base import AsyncSession
from app.logging import get_logger

router = Router(name="settings")
log = get_logger(__name__)


@router.callback_query(SettingsCallback.filter())
async def on_settings_action(
    query: CallbackQuery,
    callback_data: SettingsCallback,
    bot: Bot,
    session: AsyncSession,
) -> None:
    """Apply a settings-panel button press and re-render the panel."""
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return

    chat_id = message.chat.id
    if not await is_chat_admin(bot, chat_id, query.from_user.id):
        await query.answer("Только администраторы чата", show_alert=True)
        return

    group = await repo.get_group(session, chat_id)
    if group is None:
        await query.answer(texts.GROUP_UNKNOWN, show_alert=True)
        return

    action = callback_data.action
    note = "Готово"
    if action in FREQUENCY_PRESETS:
        preset = FREQUENCY_PRESETS[action]
        await repo.set_digest_times(session, chat_id, preset)
        note = f"Частота: {plural_times(len(preset))}"
    elif action == "toggle_day":
        try:
            day = int(callback_data.value)
        except ValueError:
            await query.answer("Не удалось распознать день недели", show_alert=True)
            return

        current_days = canonical_weekdays(group.digest_days)
        if day in current_days:
            if len(current_days) == 1:
                await query.answer("Нужно оставить хотя бы один день", show_alert=True)
                return
            new_days = [value for value in current_days if value != day]
        else:
            new_days = canonical_weekdays([*current_days, day])
        await repo.set_digest_days(session, chat_id, new_days)
        note = f"Дни: {format_weekdays(new_days)}"
    elif action == "pause":
        await repo.set_paused(session, chat_id, True)
        note = "Дайджест на паузе"
    elif action == "resume":
        await repo.set_paused(session, chat_id, False)
        note = "Дайджест возобновлён"
    # `refresh` falls through — the panel is simply re-rendered below.

    log.info("settings.changed", chat_id=chat_id, action=action)

    # `group` is the identity-mapped object the repo helpers just mutated.
    text, keyboard = render_settings_panel(group)
    # "message is not modified" (e.g. a no-op refresh) is harmless.
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await query.answer(note)
