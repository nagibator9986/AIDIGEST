"""Application configuration — a single, validated, cached Settings object.

All runtime knobs live here and are loaded from environment variables / `.env`.
Nothing else in the codebase should read `os.environ` directly.
"""

from __future__ import annotations

import os
import zoneinfo
from collections.abc import Sequence
from datetime import time
from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError

_RAW_CSV_FIELDS = {"admin_ids", "extra_rss_feeds"}


def _coerce_async_database_url(value: object) -> object:
    """Rewrite platform Postgres URLs to the async driver used by the app."""
    if isinstance(value, str):
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix) :]
    return value


def _running_on_railway() -> bool:
    """Railway injects several RAILWAY_* variables into deployed services."""
    return any(key.startswith("RAILWAY_") for key in os.environ)


def _database_url_points_to_localhost(value: str) -> bool:
    return "@localhost:" in value or "@127.0.0.1:" in value or "@[::1]:" in value


def _validate_database_url_format(value: str) -> str:
    try:
        make_url(value)
    except ArgumentError as exc:
        raise ValueError(
            "DATABASE_URL has invalid format. Use a plain Postgres URL like "
            "'postgresql://user:password@host:5432/database' or a Railway "
            "reference that resolves to one, for example '${{Postgres.DATABASE_URL}}'."
        ) from exc
    return value


def _validate_managed_database_url(value: str) -> str:
    _validate_database_url_format(value)
    if _running_on_railway() and (
        not os.getenv("DATABASE_URL") or _database_url_points_to_localhost(value)
    ):
        raise ValueError(
            "DATABASE_URL is not configured for this Railway service. "
            "Attach a PostgreSQL database and set the bot service DATABASE_URL "
            "variable to the database connection string/reference."
        )
    return value


class _RawCsvEnvSource(EnvSettingsSource):
    """Keep selected env vars as raw strings so validators can parse CSV values."""

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        if field_name in _RAW_CSV_FIELDS and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class _RawCsvDotEnvSource(DotEnvSettingsSource):
    """Dotenv variant of :class:`_RawCsvEnvSource`."""

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        if field_name in _RAW_CSV_FIELDS and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    """Validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Telegram ───────────────────────────────────────────────────────────
    bot_token: SecretStr = Field(..., description="Token from @BotFather")

    # ── Gemini ─────────────────────────────────────────────────────────────
    gemini_api_key: SecretStr = Field(..., description="Google AI Studio key")
    # flash: strong quality/cost balance for scoring + summarisation.
    gemini_model: str = "gemini-2.5-flash"
    # Max items sent to Gemini per scoring run — a cost cap. The highest-value
    # RAW items are scored first, so a smaller budget still feeds a good digest.
    scoring_budget: int = Field(default=40, ge=1, le=1000)

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://aidigest:aidigest@localhost:5432/aidigest"

    # ── Digest behaviour ───────────────────────────────────────────────────
    digest_time: str = "09:00"
    timezone: str = "Europe/Moscow"
    digest_size: int = Field(default=5, ge=1, le=20)
    score_threshold: int = Field(default=7, ge=1, le=10)

    # ── Ingestion ──────────────────────────────────────────────────────────
    ingest_interval_hours: int = Field(default=3, ge=1, le=24)
    # How far back to consider news, in days. Collectors fetch this window and
    # the digest selects the best still-relevant items from it — so the digest
    # is "the most important AI news right now", not strictly the last 24h.
    lookback_days: int = Field(default=7, ge=1, le=90)
    hn_min_score: int = Field(default=100, ge=0)
    extra_rss_feeds: list[str] = Field(default_factory=list)

    # ── Operators ──────────────────────────────────────────────────────────
    admin_ids: list[int] = Field(default_factory=list)

    # ── Product Hunt (optional) ────────────────────────────────────────────
    producthunt_token: SecretStr | None = None

    # ── Observability ──────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_json: bool = True

    # ── Network ────────────────────────────────────────────────────────────
    request_timeout: float = 20.0
    http_user_agent: str = "AI-Insight-Digest/1.0 (+https://github.com/ai-insight-digest)"

    # ── Validators ─────────────────────────────────────────────────────────
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _RawCsvEnvSource(settings_cls),
            _RawCsvDotEnvSource(
                settings_cls,
                env_file=settings_cls.model_config.get("env_file"),
                env_file_encoding=settings_cls.model_config.get("env_file_encoding"),
            ),
            file_secret_settings,
        )

    @field_validator("admin_ids", "extra_rss_feeds", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept comma-separated strings for list-typed env vars."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("producthunt_token", mode="before")
    @classmethod
    def _blank_secret_is_none(cls, value: object) -> object:
        """Treat an empty/whitespace env var (e.g. ``PRODUCTHUNT_TOKEN=``) as unset."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _async_database_url(cls, value: object) -> object:
        """Rewrite a plain Postgres URL to the async ``asyncpg`` driver.

        Managed platforms (Railway, Heroku, Render) inject ``DATABASE_URL`` as
        ``postgres://`` / ``postgresql://``; the app needs ``+asyncpg``.
        """
        return _coerce_async_database_url(value)

    @field_validator("digest_time")
    @classmethod
    def _validate_digest_time(cls, value: str) -> str:
        parse_hhmm(value)  # raises ValueError on bad input
        return value

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            zoneinfo.ZoneInfo(value)
        except zoneinfo.ZoneInfoNotFoundError as exc:  # pragma: no cover
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def _validate_deploy_database_url(self) -> Settings:
        self.database_url = _validate_managed_database_url(self.database_url)
        return self

    # ── Derived helpers ────────────────────────────────────────────────────
    @property
    def tz(self) -> zoneinfo.ZoneInfo:
        return zoneinfo.ZoneInfo(self.timezone)

    @property
    def default_digest_time(self) -> time:
        return parse_hhmm(self.digest_time)

    @property
    def lookback_seconds(self) -> int:
        return self.lookback_days * 86_400


# Hard ceiling on how many digests a chat may receive per day.
MAX_DIGESTS_PER_DAY = 8
ALL_DIGEST_WEEKDAYS = [1, 2, 3, 4, 5, 6, 7]

_WEEKDAY_ALIASES: dict[str, int] = {
    "1": 1,
    "mon": 1,
    "monday": 1,
    "пн": 1,
    "пон": 1,
    "понедельник": 1,
    "2": 2,
    "tue": 2,
    "tues": 2,
    "tuesday": 2,
    "вт": 2,
    "вторник": 2,
    "3": 3,
    "wed": 3,
    "wednesday": 3,
    "ср": 3,
    "среда": 3,
    "4": 4,
    "thu": 4,
    "thur": 4,
    "thurs": 4,
    "thursday": 4,
    "чт": 4,
    "четверг": 4,
    "5": 5,
    "fri": 5,
    "friday": 5,
    "пт": 5,
    "пятница": 5,
    "6": 6,
    "sat": 6,
    "saturday": 6,
    "сб": 6,
    "суббота": 6,
    "7": 7,
    "sun": 7,
    "sunday": 7,
    "вс": 7,
    "воскресенье": 7,
}
_ALL_WEEKDAY_TOKENS = {"all", "daily", "everyday", "все", "ежедневно"}


def parse_hhmm(value: str) -> time:
    """Parse an ``HH:MM`` string into a :class:`datetime.time`.

    Raises :class:`ValueError` for malformed input — used both for validation
    and by the ``/digest_time`` command handler.
    """
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {value!r}")
    hour, minute = (int(p) for p in parts)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time out of range: {value!r}")
    return time(hour=hour, minute=minute)


def normalize_schedule(times: list[str]) -> list[str]:
    """Validate, normalise, de-duplicate and sort a list of ``HH:MM`` slots.

    Returns canonical ``"HH:MM"`` strings in ascending order. Raises
    :class:`ValueError` on a malformed slot, an empty list, or too many slots.
    """
    canonical: set[str] = set()
    for raw in times:
        canonical.add(parse_hhmm(raw).strftime("%H:%M"))
    if not canonical:
        raise ValueError("Schedule must contain at least one time")
    if len(canonical) > MAX_DIGESTS_PER_DAY:
        raise ValueError(f"At most {MAX_DIGESTS_PER_DAY} delivery times are allowed")
    return sorted(canonical)


def normalize_weekdays(days: Sequence[str | int]) -> list[int]:
    """Validate and normalise delivery weekdays into ISO day numbers ``1..7``."""
    canonical: set[int] = set()
    for raw in days:
        if isinstance(raw, int):
            day = raw
        else:
            token = raw.strip().lower()
            if not token:
                raise ValueError("Weekday token must not be blank")
            if token in _ALL_WEEKDAY_TOKENS:
                canonical.update(ALL_DIGEST_WEEKDAYS)
                continue
            resolved = _WEEKDAY_ALIASES.get(token)
            if resolved is None:
                raise ValueError(f"Unknown weekday: {raw!r}")
            day = resolved
        if day not in ALL_DIGEST_WEEKDAYS:
            raise ValueError(f"Weekday out of range: {raw!r}")
        canonical.add(day)
    if not canonical:
        raise ValueError("At least one delivery weekday is required")
    return sorted(canonical)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


class DatabaseSettings(BaseSettings):
    """Minimal settings for tools that only need a database connection."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Settings.model_fields["database_url"].default

    @field_validator("database_url", mode="before")
    @classmethod
    def _async_database_url(cls, value: object) -> object:
        return _coerce_async_database_url(value)


def get_database_url() -> str:
    """Return the database URL without requiring runtime service secrets."""
    return _validate_managed_database_url(DatabaseSettings().database_url)
