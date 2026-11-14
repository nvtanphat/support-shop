"""Public policy endpoints used by the citation modal and the related-policies panel."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.infra.db.tables import Base, PolicyChunkModel
from shopagent.rag.indexer import index_policies
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
async def policy_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_lists_clauses_in_force_with_title_and_version(policy_client) -> None:  # type: ignore[no-untyped-def]
    client, factory = policy_client
    assert (await client.get("/policies")).json() == {"policies": []}  # nothing indexed yet: empty, not invented
    async with factory() as session:
        await index_policies(session)
    body = (await client.get("/policies")).json()["policies"]
    ids = [p["clause_id"] for p in body]
    assert "POL-RETURN-01" in ids and ids == sorted(ids)
    first = next(p for p in body if p["clause_id"] == "POL-RETURN-02")
    assert first["version"] and first["title"].startswith("Chính sách đổi trả do khách hàng đổi ý")
    assert not first["title"].endswith(".")


@pytest.mark.asyncio
async def test_clause_detail_returns_text_and_hides_expired_clauses(policy_client) -> None:  # type: ignore[no-untyped-def]
    client, factory = policy_client
    async with factory() as session:
        await index_policies(session)
    detail = await client.get("/policies/pol-return-02")  # ids are case-insensitive
    assert detail.status_code == 200 and "7 ngày" in detail.json()["text"]
    assert (await client.get("/policies/POL-NOPE-99")).status_code == 404

    async with factory() as session:
        await session.execute(update(PolicyChunkModel).values(effective_to=datetime(2026, 1, 1, tzinfo=UTC)))
        await session.commit()
    assert (await client.get("/policies")).json() == {"policies": []}
    assert (await client.get("/policies/POL-RETURN-02")).status_code == 404
