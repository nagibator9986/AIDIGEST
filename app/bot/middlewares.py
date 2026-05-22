"""aiogram middlewares.

:class:`DbSessionMiddleware` opens one transactional :class:`AsyncSession` per
update and injects it into every handler as the ``session`` keyword argument,
committing on success and rolling back on any exception.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.db.base import get_sessionmaker
from app.logging import get_logger

log = get_logger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Provide a per-update database session to handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with get_sessionmaker()() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class ErrorLoggingMiddleware(BaseMiddleware):
    """Log unhandled handler exceptions without crashing the dispatcher."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            log.error(
                "handler.error",
                event_type=type(event).__name__,
                error=str(exc),
                exc_info=True,
            )
            return None
