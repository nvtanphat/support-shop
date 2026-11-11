"""Resilience and fault injection tests enforcing S1-S6 invariants and idempotency."""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shopagent.api.app import app
from shopagent.api.deps import get_db_session
from shopagent.core.clock import get_clock
from shopagent.core.principal import Principal
from shopagent.core.security import create_access_token
from shopagent.infra.db.tables import (
    Base,
    CustomerModel,
    CustomerCredentialsModel,
    OrderModel,
    PendingActionModel,
    RefundModel,
    OutboxEventModel,
)
from shopagent.infra.worker.outbox_worker import process_outbox_batch


@pytest.fixture
async def res_session_factory():
    now = get_clock().now()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_worker_idempotency_and_processing(res_session_factory):
    """Verify outbox worker processes refund.execute events and is idempotent."""
    async with res_session_factory() as session:
        customer_id = uuid.uuid4()
        order_id = uuid.uuid4()
        refund_id = uuid.uuid4()

        # Seed customer
        cust = CustomerModel(
            id=customer_id,
            email="res@example.vn",
            phone="0909999888",
            full_name="Resilience Tester",
        )
        session.add(cust)

        now = get_clock().now()
        # Seed order and refund
        order = OrderModel(
            id=order_id,
            code="SL-RES-01",
            customer_id=customer_id,
            status="delivered",
            payment_method="bank_transfer",
            payment_status="paid",
            subtotal=300000,
            discount_total=0,
            shipping_fee=0,
            total=300000,
            placed_at=now,
        )
        session.add(order)

        refund = RefundModel(
            id=refund_id,
            code="RF-RES-01",
            order_id=order_id,
            amount=150000,
            status="processing",
            attempts=0,
        )
        session.add(refund)

        # Seed outbox event
        event = OutboxEventModel(
            id=uuid.uuid4(),
            type="refund.execute",
            payload={"refund_id": str(refund_id), "amount": 150000},
            status="pending",
            idempotency_key="rf-res-01-key",
            next_attempt_at=now - timedelta(minutes=1),
        )
        session.add(event)
        await session.commit()

    # Run outbox worker batch
    async with res_session_factory() as session:
        processed = await process_outbox_batch(session)
        assert processed == 1

        # Check refund status succeeded
        stmt_ref = select(RefundModel).where(RefundModel.id == refund_id)
        res_ref = await session.execute(stmt_ref)
        updated_ref = res_ref.scalar_one()
        assert updated_ref.status == "succeeded"
        assert updated_ref.gateway_txn_id is not None
        assert updated_ref.gateway_txn_id.startswith("GW-")

    # Second run should process 0 items (idempotent)
    async with res_session_factory() as session:
        processed_again = await process_outbox_batch(session)
        assert processed_again == 0


@pytest.mark.asyncio
async def test_action_expiration_and_tampered_hash_rejection(res_session_factory):
    """Verify expired actions cannot be confirmed, and tampered hash is rejected (S1 invariant)."""
    async with res_session_factory() as session:
        customer_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        action_active_id = uuid.uuid4()
        action_expired_id = uuid.uuid4()

        # Seed customer
        cust = CustomerModel(
            id=customer_id,
            email="victim@example.vn",
            phone="0901234567",
            full_name="Victim Customer",
        )
        session.add(cust)

        order_act_id = uuid.uuid4()
        order_exp_id = uuid.uuid4()

        now = get_clock().now()
        # Seed active action
        active_action = PendingActionModel(
            id=action_active_id,
            conversation_id=conv_id,
            customer_id=customer_id,
            type="cancel_order",
            payload={"order_id": str(order_act_id), "order_code": "SL-ACT-01"},
            payload_hash="valid_hash_123",
            preview={"title": "Hủy đơn"},
            status="proposed",
            presented_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        session.add(active_action)

        # Seed expired action
        expired_action = PendingActionModel(
            id=action_expired_id,
            conversation_id=conv_id,
            customer_id=customer_id,
            type="cancel_order",
            payload={"order_id": str(order_exp_id), "order_code": "SL-EXP-01"},
            payload_hash="valid_hash_456",
            preview={"title": "Hủy đơn"},
            status="proposed",
            presented_at=now - timedelta(hours=1),
            expires_at=now - timedelta(minutes=30),  # expired
        )
        session.add(expired_action)
        await session.commit()

    async def override_db():
        async with res_session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = override_db
    transport = ASGITransport(app=app)

    token = create_access_token({"sub": str(customer_id), "role": "customer", "customer_id": str(customer_id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Attempt 1: Confirm with wrong/tampered hash on active action
            res_tampered = await client.post(
                f"/actions/{action_active_id}/confirm",
                headers=headers,
                json={"preview_hash": "wrong_hash"},
            )
            assert res_tampered.status_code == 400
            assert "bản xem trước" in res_tampered.json()["detail"]["message"].lower()

            # Attempt 2: Confirm on expired action
            res_expired = await client.post(
                f"/actions/{action_expired_id}/confirm",
                headers=headers,
                json={"preview_hash": "valid_hash_456"},
            )
            assert res_expired.status_code == 400
            assert "hết hạn" in res_expired.json()["detail"]["message"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_durable_checkpointer_persistence_across_restart(tmp_path):
    """Verify DurableCheckpointer saves checkpoints to disk and restores state across restarts."""
    from shopagent.agent.checkpoint import DurableCheckpointer

    ckpt_file = tmp_path / "checkpoints_test.pkl"
    cp1 = DurableCheckpointer(storage_path=ckpt_file)

    config_t1 = {"configurable": {"thread_id": "thread-user-42", "checkpoint_ns": ""}}
    ckpt_t1 = {
        "v": 1,
        "id": "chk-001",
        "ts": "2026-11-11T12:00:00Z",
        "channel_values": {"messages": ["Xin chào", "Cần hỗ trợ đổi đơn SL-8F3D9K"], "step": 1},
        "channel_versions": {"messages": 1, "step": 1},
        "versions_seen": {},
    }
    cp1.put(config_t1, ckpt_t1, {}, {"messages": 1, "step": 1})

    # Verify file is persisted
    assert ckpt_file.exists()

    # Simulate process restart by creating a new checkpointer from disk
    cp2 = DurableCheckpointer(storage_path=ckpt_file)
    restored_tuple = cp2.get_tuple(config_t1)

    assert restored_tuple is not None
    assert restored_tuple.checkpoint["id"] == "chk-001"
    assert restored_tuple.checkpoint["channel_values"]["messages"] == [
        "Xin chào",
        "Cần hỗ trợ đổi đơn SL-8F3D9K",
    ]
    assert restored_tuple.checkpoint["channel_values"]["step"] == 1

    # Verify updating a restored thread in a new namespace works without error
    config_t1_ns = {"configurable": {"thread_id": "thread-user-42", "checkpoint_ns": "sub_workflow"}}
    ckpt_t1_ns = {
        "v": 1,
        "id": "chk-sub-001",
        "ts": "2026-11-11T12:01:00Z",
        "channel_values": {"sub_status": "in_progress"},
        "channel_versions": {"sub_status": 1},
        "versions_seen": {},
    }
    cp2.put(config_t1_ns, ckpt_t1_ns, {}, {"sub_status": 1})

    # Third checkpointer instance should have both
    cp3 = DurableCheckpointer(storage_path=ckpt_file)
    t1_loaded = cp3.get_tuple(config_t1)
    t1_ns_loaded = cp3.get_tuple(config_t1_ns)
    assert t1_loaded.checkpoint["channel_values"]["step"] == 1
    assert t1_ns_loaded.checkpoint["channel_values"]["sub_status"] == "in_progress"

    # Verify delete_thread
    cp3.delete_thread("thread-user-42")
    cp4 = DurableCheckpointer(storage_path=ckpt_file)
    assert cp4.get_tuple(config_t1) is None

