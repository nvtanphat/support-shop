"""Handoff, takeover and hand-back must reach the other side, not only the database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.core.security import create_access_token
from shopagent.infra.db.tables import (
    ApprovalRequestModel,
    Base,
    ConversationEventModel,
    CustomerModel,
    StaffUserModel,
    TicketModel,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

CUSTOMER, AGENT = uuid.uuid4(), uuid.uuid4()


def bearer(sub: uuid.UUID, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(sub), 'email': 'x@example.com', 'role': role})}"}


@pytest.fixture
async def env():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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


async def events(factory, conv_id: str) -> list[tuple[str, dict]]:  # type: ignore[no-untyped-def]
    async with factory() as session:
        rows = (await session.execute(select(ConversationEventModel).where(ConversationEventModel.conversation_id == uuid.UUID(conv_id)).order_by(ConversationEventModel.seq))).scalars().all()
        return [(r.type, r.payload) for r in rows]


@pytest.mark.asyncio
async def test_full_takeover_round_trip_reaches_both_sides(env) -> None:  # type: ignore[no-untyped-def]
    client, factory = env
    customer, staff = bearer(CUSTOMER, "customer"), bearer(AGENT, "agent")
    conv = (await client.post("/conversations", json={}, headers=customer)).json()["id"]

    assert (await client.post(f"/conversations/{conv}/handoff", json={}, headers=customer)).status_code == 200
    await client.post(f"/conversations/{conv}/messages", json={"content": "Mình cần người hỗ trợ gấp"}, headers=customer)

    (ticket,) = (await client.get("/staff/tickets", headers=staff)).json()["tickets"]
    assert (await client.post(f"/staff/tickets/{ticket['id']}/claim", headers=staff)).status_code == 200
    # A claimed ticket stays in the default queue so the agent can keep working on it.
    queue = (await client.get("/staff/tickets", headers=staff)).json()["tickets"]
    assert [(t["id"], t["status"]) for t in queue] == [(ticket["id"], "assigned")]

    # Staff can read what the customer wrote while waiting.
    thread = (await client.get(f"/conversations/{conv}", headers=staff)).json()["messages"]
    assert [m["content"] for m in thread] == ["Mình cần người hỗ trợ gấp"]

    await client.post(f"/staff/conversations/{conv}/messages", json={"content": "Chào bạn, mình là nhân viên."}, headers=staff)
    assert (await client.post(f"/staff/conversations/{conv}/return-to-ai", headers=staff)).status_code == 200

    stream = await events(factory, conv)
    assert ("conversation.mode_changed", {"mode": "waiting_human"}) in stream
    assert ("conversation.mode_changed", {"mode": "human"}) in stream
    assert stream[-1] == ("conversation.mode_changed", {"mode": "ai"})
    staff_messages = [p for kind, p in stream if kind == "message.completed" and p.get("role") == "staff"]
    assert [p["content"] for p in staff_messages] == ["Chào bạn, mình là nhân viên."]

    # Handing back resolves the ticket, so it leaves the queue.
    assert (await client.get("/staff/tickets", headers=staff)).json()["tickets"] == []


@pytest.mark.asyncio
async def test_approval_queue_uses_the_field_names_the_portal_reads(env) -> None:  # type: ignore[no-untyped-def]
    client, factory = env
    subject = uuid.uuid4()
    async with factory() as session:
        session.add(ApprovalRequestModel(subject_type="return_request", subject_id=subject, gate="A_return", required_role="agent", status="pending", requested_at=datetime.now(UTC)))
        await session.commit()
    (row,) = (await client.get("/staff/approvals", headers=bearer(AGENT, "agent"))).json()["approvals"]
    assert row["subject_type"] == "return_request" and row["subject_id"] == str(subject)
    assert row["requested_at"]
    async with factory() as session:
        assert (await session.execute(select(TicketModel))).scalars().all() == []
