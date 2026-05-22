"""Shared pytest fixtures.

Required secrets are injected into the environment *before* any application
module is imported, so :func:`app.config.get_settings` validates cleanly.
"""

from __future__ import annotations

import os

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ADMIN_IDS", "111,222")

import pytest_asyncio
from app.db import models  # noqa: F401  -- registers tables on Base
from app.db.base import Base
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """A fresh in-memory SQLite database with the full schema, per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session

    await engine.dispose()
