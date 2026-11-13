"""The seed data respects every foreign key, in an order PostgreSQL accepts.

SQLite does not enforce foreign keys unless asked, so a seeder that inserts a child row before its parent passes
every SQLite-backed test and then fails on PostgreSQL. Here SQLite is told to enforce them.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from shopagent.domain.seeder import generate_seed_data
from shopagent.infra.db.tables import Base
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


@pytest.fixture
async def strict_session():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enforce_foreign_keys(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)() as session:
        yield session
    await engine.dispose()


async def test_seed_inserts_parents_before_children(strict_session: AsyncSession) -> None:
    counts = await generate_seed_data(strict_session, now=NOW, num_customers=10, num_products=10, num_orders=400)
    assert counts["returns"] > 0 and counts["demo_orders"] == 24
    assert (await strict_session.execute(text("PRAGMA foreign_key_check"))).all() == []
    refunds = (await strict_session.execute(text("SELECT count(*) FROM refunds"))).scalar_one()
    assert refunds > 0  # the case that failed on PostgreSQL: refunds reference seeded return requests
