"""Async SQLAlchemy engine, session factory and declarative base.

The engine is created lazily so that importing this module never requires a
reachable database (important for migrations, tests and CLI ``--help``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        url = get_settings().database_url
        # SQLite (tests) does not support pool sizing arguments.
        kwargs: dict[str, object] = {"echo": False, "future": True}
        if not url.startswith("sqlite"):
            kwargs |= {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}
        _engine = create_async_engine(url, **kwargs)
        log.debug("db.engine_created", dialect=url.split("://", 1)[0])
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope: commit on success, roll back on any exception.

    This is the single sanctioned way to obtain a session outside of the
    aiogram middleware (which manages its own per-update session).
    """
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Dispose the engine on graceful shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
        log.debug("db.engine_disposed")
