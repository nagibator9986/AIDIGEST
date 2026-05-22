"""Static user-facing text. Centralised so wording is easy to audit and tune.

All strings are plain text rendered with ``ParseMode.HTML``; dynamic values
interpolated into them must be HTML-escaped by the caller.
"""

from __future__ import annotations

WELCOME_GROUP = (
    "👋 <b>AI Insight Digest</b> на связи!\n\n"
    "Я буду присылать сюда дайджест из <b>топ-событий мира AI</b>: релизы "
    "моделей, практичные open-source инструменты и значимые исследования. "
    "Каждую новость оценивает ИИ-редактор на базе Gemini — он отсеивает "
    "маркетинговый шум.\n\n"
    "📅 Сейчас доставка настроена на <b>{time}</b> ({tz}).\n\n"
    "<b>Настройка прямо в чате</b> (для администраторов):\n"
    "• /settings — панель настроек: частота, дни, пауза\n"
    "• /digest_time 09:00 18:00 — своё расписание (1–8 раз в день)\n"
    "• /digest_days пн ср пт — дни недели для плановых новостей\n"
    "• /timezone Europe/Moscow — часовой пояс\n"
    "• /digest_now — прислать дайджест сейчас\n\n"
    "Права администратора мне не нужны — достаточно возможности писать."
)

START_PRIVATE = (
    "👋 Привет! Я <b>AI Insight Digest</b> — ежедневный дайджест значимых "
    "новостей из мира искусственного интеллекта.\n\n"
    "Добавьте меня в групповой чат — и там будет появляться подборка топ-"
    "новостей AI, отобранных и прокомментированных ИИ-редактором. Расписание "
    "настраивается прямо в чате командой /settings.\n\n"
    "Команда /help — подробнее."
)

HELP = (
    "<b>AI Insight Digest — справка</b>\n\n"
    "Я собираю новости AI из первоисточников (OpenAI, Google DeepMind, "
    "Hugging Face), деловой тех-прессы (TechCrunch, VentureBeat), Hacker News "
    "и GitHub Trending, "
    "оцениваю каждую через Gemini и присылаю в чаты дайджест по расписанию.\n\n"
    "<b>Команды в чате (для администраторов):</b>\n"
    "• /settings — панель настроек с кнопками\n"
    "• /digest_time 09:00 18:00 — задать время(-ена) доставки\n"
    "• /digest_days пн ср пт — выбрать дни недели\n"
    "• /timezone Europe/Moscow — часовой пояс чата\n"
    "• /digest_now — прислать дайджест немедленно\n"
    "• /status — текущие настройки\n"
)

# ── Settings panel ─────────────────────────────────────────────────────────
SETTINGS_PANEL = (
    "⚙️ <b>Настройки дайджеста</b>\n\n"
    "🕐 Время доставки: <b>{times}</b>\n"
    "📊 Частота: <b>{freq}</b>\n"
    "📅 Дни отправки: <b>{days}</b>\n"
    "🌍 Часовой пояс: <b>{tz}</b>\n"
    "{status_line}\n\n"
    "Быстрая настройка частоты и дней — кнопками ниже.\n"
    "Своё расписание: <code>/digest_time 08:00 14:00 20:00</code>\n"
    "Дни недели: <code>/digest_days пн ср пт</code>\n"
    "Часовой пояс: <code>/timezone Asia/Almaty</code>"
)
SETTINGS_STATUS_ACTIVE = "▶️ Статус: <b>активен</b>"
SETTINGS_STATUS_PAUSED = "⏸ Статус: <b>на паузе</b>"

# ── Schedule commands ──────────────────────────────────────────────────────
NOT_GROUP = "Эта команда работает только в групповых чатах и каналах."
NOT_CHAT_ADMIN = "⛔️ Эта команда доступна только администраторам чата."
NOT_BOT_ADMIN = "⛔️ Эта команда доступна только администраторам бота."
GROUP_UNKNOWN = "Чат не зарегистрирован. Удалите и снова добавьте меня в чат."

DIGEST_TIME_USAGE = (
    "Укажите одно или несколько значений времени через пробел.\n"
    "Например: <code>/digest_time 09:00 18:00</code> — дайджест дважды в день.\n"
    "Максимум 8 значений."
)
DIGEST_TIME_BAD = (
    "❌ Неверный формат. Используйте <code>ЧЧ:ММ</code> через пробел, "
    "например <code>/digest_time 09:00 14:00 20:00</code> (макс. 8)."
)
DIGEST_TIME_OK = "✅ Расписание обновлено: <b>{times}</b> — {freq} ({tz})."

DIGEST_DAYS_USAGE = (
    "Укажите дни недели через пробел.\n"
    "Например: <code>/digest_days пн ср пт</code> или <code>/digest_days 1 3 5</code>.\n"
    "Можно также использовать <code>/digest_days все</code>."
)
DIGEST_DAYS_BAD = (
    "❌ Неверный формат дней недели. Примеры: "
    "<code>/digest_days пн ср пт</code>, <code>/digest_days 1 3 5</code>, "
    "<code>/digest_days все</code>."
)
DIGEST_DAYS_OK = "✅ Дни отправки обновлены: <b>{days}</b>."

TIMEZONE_USAGE = (
    "Укажите часовой пояс в формате IANA.\n"
    "Например: <code>/timezone Europe/Moscow</code> или "
    "<code>/timezone Asia/Almaty</code>"
)
TIMEZONE_BAD = (
    "❌ Неизвестный часовой пояс. Примеры: <code>Europe/Moscow</code>, "
    "<code>Asia/Almaty</code>, <code>Europe/Kyiv</code>."
)
TIMEZONE_OK = "✅ Часовой пояс чата изменён на <b>{tz}</b>."

PAUSED_OK = "⏸ Дайджест поставлен на паузу. Возобновить — кнопкой в /settings."
RESUMED_OK = "▶️ Дайджест возобновлён."

# ── Manual digest ──────────────────────────────────────────────────────────
DIGEST_SENDING = "⏳ Собираю свежий дайджест…"
DIGEST_SENT = "✅ Готово — дайджест отправлен ({count} новостей)."
DIGEST_FAILED = "❌ Не удалось отправить дайджест. Попробуйте позже."

# ── Admin ──────────────────────────────────────────────────────────────────
ADMIN_STATS = (
    "📈 <b>Статистика бота</b>\n\n"
    "👥 Активных чатов: <b>{active_groups}</b> (всего {total_groups})\n\n"
    "🗞 <b>Новости в пуле:</b>\n{news_lines}"
)
ADMIN_RUN_STARTED = "⏳ Запускаю: <b>{task}</b>…"
ADMIN_INGEST_DONE = "✅ Сбор завершён: {summary}"
ADMIN_SCORING_DONE = "✅ Скоринг завершён: {summary}"
