"""Timezone-aware time helpers."""

from __future__ import annotations

import zoneinfo
from datetime import UTC, datetime, tzinfo


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def now_in(tz_name: str) -> datetime:
    """Current time in the named timezone (falls back to UTC if unknown)."""
    tz: tzinfo
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except zoneinfo.ZoneInfoNotFoundError:
        tz = UTC
    return datetime.now(tz)


def ensure_aware(dt: datetime) -> datetime:
    """Attach UTC tzinfo to a naive datetime; pass through aware datetimes."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
