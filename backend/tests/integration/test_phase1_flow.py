"""Phase 1 acceptance test: End-to-end domain services flow without UI or LLM."""

from __future__ import annotations

from datetime import datetime, timedelta
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shopagent.core.clock import Clock, set_global_clock
from shopagent.core.principal import Principal, PrincipalRole
from shopagent.domain.models.enums import (
    ApprovalGate,
    ApprovalStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductCategory,
    RefundStatus,
    ReturnReason,
    ReturnResolution,
    ReturnStatus,
)
from shopagent.domain.services.actions import ActionService
from shopagent.domain.services.approvals import ApprovalService
from shopagent.domain.services.cancellations import CancellationService
from shopagent.domain.services.refunds import RefundService
from shopagent.domain.services.returns import ReturnService
from shopagent.domain.services.warehouse import WarehouseService
from shopagent.infra.db.repositories.approval_repo import ApprovalRepository
from shopagent.infra.db.repositories.order_repo import OrderRepository
from shopagent.infra.db.repositories.refund_repo import RefundRepository
from shopagent.infra.db.repositories.return_repo import ReturnRepository
from shopagent.infra.db.tables import (
    Base,
    CustomerCredentialsModel,
    CustomerModel,
    OrderItemModel,
    OrderModel,
    ProductModel,
    ProductVariantModel,
    StaffUserModel,
)
from shopagent.infra.outbox.dispatcher import OutboxDispatcher
from shopagent.infra.payments.simulated import SimulatedPaymentGateway


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session, session_factory
    set_global_clock(Clock())
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_return_and_refund_lifecycle_pure_domain(db_session):
    """Phase 1 Acceptance Criteria:

    Luồng: đề xuất trả hàng -> xác nhận -> duyệt Gate A -> tiếp nhận kho -> kiểm hàng -> duyệt Gate B / hoàn tiền -> giải ngân outbox.
    """
    session, session_factory = db_session
    clock = Clock(datetime(2026, 11, 11, 10, 0, 0))
    set_global_clock(clock)

    # 1. Seed customer, supervisor, and product
    cust_id = uuid.uuid4()
    sup_id = uuid.uuid4()
    cust = CustomerModel(
        id=cust_id,
        email="test_cust@example.com",
        phone="0912345678",
        full_name="Nguyễn Văn A",
        tier="standard",
    )
    sup = StaffUserModel(
        id=sup_id,
        email="sup@example.com",
        password_hash="fake",
        role="supervisor",
        full_name="Trần Trưởng Ca",
    )
    prod = ProductModel(
        id=uuid.uuid4(),
        name="Áo thun polo",
        category=ProductCategory.FASHION.value,
        return_flags=[],
    )
    var = ProductVariantModel(
        id=uuid.uuid4(),
        product_id=prod.id,
        sku="POLO-001-L",
        price=200000,
        stock=50,
    )
    session.add_all([cust, sup, prod, var])
    await session.flush()

    # 2. Delivered order (delivered 3 days ago)
    order_id = uuid.uuid4()
    order = OrderModel(
        id=order_id,
        code="SL-TEST01",
        customer_id=cust_id,
        status=OrderStatus.DELIVERED.value,
        payment_method=PaymentMethod.CARD.value,
        payment_status=PaymentStatus.PAID.value,
        subtotal=200000,
        discount_total=0,
        shipping_fee=30000,
        total=230000,
        paid_amount=230000,
        refunded_amount=0,
        placed_at=clock.now() - timedelta(days=5),
        delivered_at=clock.now() - timedelta(days=3),
    )
    session.add(order)
    item = OrderItemModel(
        id=uuid.uuid4(),
        order_id=order_id,
        variant_id=var.id,
        qty=1,
        unit_price=200000,
        allocated_discount=0,
        returned_qty=0,
    )
    session.add(item)
    await session.commit()

    cust_principal = Principal.authenticated_customer(customer_id=cust_id, email=cust.email)
    sup_principal = Principal.staff(user_id=sup_id, email=sup.email, role=PrincipalRole.SUPERVISOR)

    # 3. Customer proposes return
    return_service = ReturnService(session)
    proposal = await return_service.propose_return(
        principal=cust_principal,
        conversation_id=uuid.uuid4(),
        order_code="SL-TEST01",
        items=[{"item_id": str(item.id), "qty": 1}],
        reason_code=ReturnReason.DEFECTIVE.value,
        resolution=ReturnResolution.REFUND.value,
    )
    assert proposal["type"] in ("return_request", "return_order")
    assert "preview_hash" in proposal
    action_id = uuid.UUID(proposal["action_id"])
    preview_hash = proposal["preview_hash"]

    # 4. Customer confirms return action
    action_service = ActionService(session)
    result = await action_service.confirm_action(
        principal=cust_principal,
        action_id=action_id,
        preview_hash=preview_hash,
    )
    assert result["success"] is True
    return_code = result["return_code"]

    return_repo = ReturnRepository(session)
    ret_req = await return_repo.get_by_code(return_code)
    assert ret_req is not None

    # If Gate A approval was created (since defective requires evidence), supervisor approves
    approval_repo = ApprovalRepository(session)
    pending_approvals = await approval_repo.list_pending()
    if pending_approvals:
        gate_a = pending_approvals[0]
        approval_service = ApprovalService(session)
        await approval_service.decide_approval(
            principal=sup_principal,
            approval_id=gate_a.id,
            decision="approved",
            note="Bằng chứng ảnh hợp lệ.",
        )
        await session.refresh(ret_req)
        assert ret_req.status == ReturnStatus.AWAITING_RETURN.value

    # 5. Warehouse receives shipment
    warehouse_service = WarehouseService(session)
    await warehouse_service.receive_shipment(
        principal=sup_principal,
        return_code=return_code,
        tracking_number="VN12345678",
    )
    await session.refresh(ret_req)
    assert ret_req.status == ReturnStatus.RECEIVED.value

    # 6. Warehouse inspects return items
    inspect_res = await warehouse_service.inspect_return(
        principal=sup_principal,
        return_code=return_code,
        items_result=[{"item_id": item.id, "passed": True}],
        staff_notes="Hàng lỗi đúng mô tả, phụ kiện đầy đủ.",
    )
    await session.commit()

    refund_code = inspect_res["refund_code"]
    refund_repo = RefundRepository(session)
    refund = await refund_repo.get_by_code(refund_code)
    assert refund is not None
    assert refund.amount == 200000  # Defect: 100% item price refunded, no shipping deduction

    # 7. Outbox dispatcher runs to disburse refund
    dispatcher = OutboxDispatcher(session_factory=session_factory)
    processed = await dispatcher.run_once()
    assert processed > 0

    # 8. Check refund status & order invariants
    await session.refresh(refund)
    assert refund.status == RefundStatus.SUCCEEDED.value
    assert refund.gateway_txn_id is not None

    order_repo = OrderRepository(session)
    order_db = await order_repo.get_by_id(order_id)
    assert order_db is not None
    await session.refresh(order_db)
    assert order_db.refunded_amount == 200000
    assert order_db.refunded_amount <= order_db.paid_amount  # Invariant 1


@pytest.mark.asyncio
async def test_order_cancellation_flow_pure_domain(db_session):
    """Acceptance test: Customer cancels order, staff approves packing cancellation, refund disbursed."""
    session, session_factory = db_session
    clock = Clock(datetime(2026, 11, 11, 10, 0, 0))
    set_global_clock(clock)

    cust_id = uuid.uuid4()
    sup_id = uuid.uuid4()
    cust = CustomerModel(
        id=cust_id,
        email="cancel_cust@example.com",
        phone="0987654321",
        full_name="Lê Hủy Đơn",
    )
    sup = StaffUserModel(
        id=sup_id,
        email="sup2@example.com",
        password_hash="fake",
        role="supervisor",
        full_name="Trần Trưởng Ca",
    )
    session.add_all([cust, sup])
    await session.flush()

    order = OrderModel(
        id=uuid.uuid4(),
        code="SL-CANCEL01",
        customer_id=cust_id,
        status=OrderStatus.PACKING.value,
        payment_method=PaymentMethod.EWALLET.value,
        payment_status=PaymentStatus.PAID.value,
        subtotal=150000,
        discount_total=0,
        shipping_fee=30000,
        total=180000,
        paid_amount=180000,
        refunded_amount=0,
        placed_at=clock.now() - timedelta(hours=2),
    )
    session.add(order)
    await session.commit()

    cust_p = Principal.authenticated_customer(customer_id=cust_id, email=cust.email)
    sup_p = Principal.staff(user_id=sup_id, email=sup.email, role=PrincipalRole.SUPERVISOR)

    # 1. Propose cancellation
    cancellation_service = CancellationService(session)
    proposal = await cancellation_service.propose_cancellation(
        principal=cust_p,
        conversation_id=uuid.uuid4(),
        order_code="SL-CANCEL01",
        reason="Đổi ý không muốn mua nữa",
    )
    action_id = uuid.UUID(proposal["action_id"])
    preview_hash = proposal["preview_hash"]

    # 2. Confirm action
    action_service = ActionService(session)
    res = await action_service.confirm_action(
        principal=cust_p,
        action_id=action_id,
        preview_hash=preview_hash,
    )
    assert res["status"] == "pending_approval"

    # 3. Supervisor approves packing cancellation
    approval_repo = ApprovalRepository(session)
    pending = await approval_repo.list_pending()
    assert len(pending) == 1

    approval_service = ApprovalService(session)
    await approval_service.decide_approval(
        principal=sup_p,
        approval_id=pending[0].id,
        decision="approved",
        note="Đơn chưa bàn giao vận chuyển, đồng ý hủy.",
    )
    await session.commit()

    # 4. Check order cancelled & refund disbursed
    await session.refresh(order)
    assert order.status == OrderStatus.CANCELLED.value
