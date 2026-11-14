"""Concurrent writers of one conversation on a real PostgreSQL server.

The customer's "talk to a person" button, staff takeover and hand-back all add events to a conversation and bump
its counters. Seen live: without the row lock that the message path already takes, two such requests at once
deadlocked or took the same event number (`uq_conv_seq`), and the customer got a 500. SQLite serialises writes, so
only PostgreSQL shows it.

Runs only when TEST_POSTGRES_URL points at a disposable PostgreSQL database; otherwise it is reported as skipped.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.core.security import create_access_token
from shopagent.infra.db.tables import Base, ConversationEventModel, CustomerModel, StaffUserModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set: PostgreSQL concurrency tests not run")

CUSTOMER, AGENT = uuid.uuid4(), uuid.uuid4()
ROUNDS = 15


def _async_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1) if url.startswith("postgresql://") else url


def bearer(sub: uuid.UUID, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(sub), 'email': 'x@example.com', 'role': role})}"}


@pytest.fixture
async def env():  # type: ignore[no-untyped-def]
    # A schema of its own, so the test neither sees nor disturbs the seeded database CI also uses.
    schema = f"concurrency_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(_async_url(POSTGRES_URL))
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(_async_url(POSTGRES_URL), connect_args={"options": f"-csearch_path={schema}"}, pool_size=10)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        session.add(CustomerModel(id=CUSTOMER, email="c@example.com", phone="0903333333", full_name="Khách"))
        session.add(StaffUserModel(id=AGENT, email="a@shop.vn", role="agent", full_name="NV", password_hash="x"))
        await session.commit()

    async def override():  # type: ignore[no-untyped-def]
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()
    async with admin.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


@pytest.mark.asyncio
async def test_handoff_takeover_and_hand_back_at_once_never_collide(env) -> None:  # type: ignore[no-untyped-def]
    client, factory = env
    customer, staff = bearer(CUSTOMER, "customer"), bearer(AGENT, "agent")
    failures: list[str] = []
    conversations: list[uuid.UUID] = []
    for _ in range(ROUNDS):
        conv = (await client.post("/conversations", json={"channel": "web"}, headers=customer)).json()["id"]
        conversations.append(uuid.UUID(conv))
        results = await asyncio.gather(
            client.post(f"/conversations/{conv}/handoff", json={"reason_code": "customer_request", "summary": "a"}, headers=customer),
            client.post(f"/staff/conversations/{conv}/messages", json={"content": "Chào bạn"}, headers=staff),
            client.post(f"/staff/conversations/{conv}/return-to-ai", headers=staff),
            client.post(f"/conversations/{conv}/handoff", json={"reason_code": "customer_request", "summary": "b"}, headers=customer),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, BaseException):
                failures.append(type(r).__name__ + ": " + str(r)[:120])
            elif r.status_code >= 500:
                failures.append(f"{r.status_code} {r.request.url.path}")
    assert failures == []

    async with factory() as session:
        for conv_id in conversations:
            seqs = (
                await session.execute(
                    select(ConversationEventModel.seq).where(ConversationEventModel.conversation_id == conv_id).order_by(ConversationEventModel.seq)
                )
            ).scalars().all()
            assert list(seqs) == list(range(1, len(seqs) + 1)), f"event numbers of {conv_id} have gaps or repeats: {seqs}"
