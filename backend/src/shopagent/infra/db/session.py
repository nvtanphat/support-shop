"""Async SQLAlchemy session and engine management."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shopagent.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.DATABASE_URL
        # In test environments without Postgres running, SQLite in-memory/file fallback can be used
        connect_args: dict[str, Any] = {}
        if "sqlite" in url:
            connect_args = {"check_same_thread": False}
            if "///" in url:
                import os
                db_path = url.split("///")[-1]
                if db_path and not db_path.startswith(":"):
                    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        _engine = create_async_engine(
            url,
            echo=False,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        engine = get_engine()
        _sessionmaker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


class _EngineProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_engine(), name)


class _SessionMakerProxy:
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return get_sessionmaker()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(get_sessionmaker(), name)


async_engine = _EngineProxy()
async_session_factory = _SessionMakerProxy()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide transactional async session context."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
