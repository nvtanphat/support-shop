"""What the UI receives and sends for a proposed action must match on every path."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.api.schemas.pending_actions import pending_action_dto
from shopagent.core.security import create_access_token
from shopagent.infra.db.tables import Base, ConversationModel, CustomerModel, PendingActionModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

OWNER = uuid.uuid4()


@pytest.fixture
async def env():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    conv_id, action_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as session:
        session.add(CustomerModel(id=OWNER, email="o@example.com", phone="0901111111", full_name="Chủ"))
        session.add(ConversationModel(id=conv_id, customer_id=OWNER))
        session.add(
            PendingActionModel(
                id=action_id, conversation_id=conv_id, customer_id=OWNER, type="return_request", payload={}, payload_hash="h" * 64,
                preview={"title": "Xác nhận yêu cầu trả hàng SL-1", "estimated_refund": 627000, "message": "Kiểm tra rồi bấm Xác nhận", "requires_evidence": True},
                status="proposed", expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        await session.commit()

    async def override():  # type: ignore[no-untyped-def]
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(OWNER), 'email': 'o@example.com', 'role': 'customer'})}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, headers, conv_id, action_id
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_conversation_detail_lists_open_proposals_in_the_shape_the_ui_reads(env) -> None:  # type: ignore[no-untyped-def]
    client, headers, conv_id, action_id = env
    resp = await client.get(f"/conversations/{conv_id}", headers=headers)  # used to be a 500: naive vs aware datetimes on SQLite
    assert resp.status_code == 200, resp.text
    (action,) = resp.json()["pending_actions"]
    assert action["id"] == str(action_id) and action["status"] == "proposed"
    assert action["payload_hash"] == "h" * 64 == action["preview_hash"]
    assert action["preview"]["estimated_refund_vnd"] == 627000 and action["preview"]["description"].startswith("Kiểm tra")


@pytest.mark.asyncio
async def test_cancel_works_without_a_request_body_and_returns_json(env) -> None:  # type: ignore[no-untyped-def]
    client, headers, _, action_id = env
    resp = await client.post(f"/actions/{action_id}/cancel", headers=headers)  # the UI sends no body
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "cancelled", "action_id": str(action_id)}
    again = await client.post(f"/actions/{action_id}/cancel", headers=headers)
    assert again.status_code == 409


def test_dto_accepts_tool_results_and_stored_rows_alike() -> None:
    from_tool = pending_action_dto(
        {"action_id": "a1", "type": "cancel_order", "preview": {"title": "t", "refund_amount": 5, "needs_approval": True}, "preview_hash": "x", "expires_at": "2026-11-13T10:00:00+00:00"},
        conversation_id="c1",
    )
    assert from_tool is not None
    assert (from_tool["id"], from_tool["payload_hash"], from_tool["status"], from_tool["conversation_id"]) == ("a1", "x", "proposed", "c1")
    assert from_tool["preview"]["estimated_refund_vnd"] == 5 and from_tool["preview"]["requires_approval"] is True
    assert pending_action_dto(None) is None
