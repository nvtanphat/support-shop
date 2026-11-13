"""Phase 1 acceptance test: End-to-end domain services flow without UI or LLM."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from shopagent.core.clock import Clock, set_global_clock
from shopagent.core.principal import Principal, PrincipalRole
from shopagent.domain.models.enums import (
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
from shopagent.domain.services.returns import ReturnService
from shopagent.domain.services.warehouse import WarehouseService
from shopagent.infra.db.repositories.approval_repo import ApprovalRepository
from shopagent.infra.db.repositories.order_repo import OrderRepository
from shopagent.infra.db.repositories.refund_repo import RefundRepository
from shopagent.infra.db.repositories.return_repo import ReturnRepository
from shopagent.infra.db.tables import (
    Base,
    CustomerModel,
    OrderItemModel,
    OrderModel,
    ProductModel,
    ProductVariantModel,
    StaffUserModel,
)
from shopagent.infra.outbox.dispatcher import OutboxDispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


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


async def add_evidence(session: AsyncSession, return_id: uuid.UUID, photos: int) -> None:
    from shopagent.infra.db.tables import EvidenceFileModel

    for index in range(photos):
        session.add(EvidenceFileModel(return_id=return_id, kind="photo", path=f"test://{index}", sha256=f"{index:064d}", size=1, uploaded_by="customer"))
    await session.flush()


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
        from shopagent.core.errors import ConflictError

        with pytest.raises(ConflictError):  # a defective-item return cannot pass gate A without the photos
            await approval_service.decide_approval(principal=sup_principal, approval_id=gate_a.id, decision="approved", note="Chưa có ảnh")
        await add_evidence(session, ret_req.id, photos=2)
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


@pytest.mark.asyncio
async def test_large_refund_needs_a_second_staff_member_and_settles_the_return(db_session):
    """Gate B path (refund above the auto limit): four-eyes, no second inspection, return leaves 'received'."""
    from shopagent.core.errors import ConflictError, ForbiddenError

    session, session_factory = db_session
    clock = Clock(datetime(2026, 11, 11, 10, 0, 0))
    set_global_clock(clock)
    cust_id, inspector_id, approver_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    prod = ProductModel(id=uuid.uuid4(), name="Áo khoác", category=ProductCategory.FASHION.value, return_flags=[])
    var = ProductVariantModel(id=uuid.uuid4(), product_id=prod.id, sku="JACKET-01", price=900000, stock=5)
    session.add_all(
        [
            CustomerModel(id=cust_id, email="big@example.com", phone="0911111111", full_name="Khách Lớn"),
            StaffUserModel(id=inspector_id, email="kho@example.com", password_hash="x", role="agent", full_name="Kho"),
            StaffUserModel(id=approver_id, email="duyet@example.com", password_hash="x", role="agent", full_name="Duyệt"),
            prod,
            var,
        ]
    )
    order_id = uuid.uuid4()
    session.add(
        OrderModel(
            id=order_id, code="SL-BIG001", customer_id=cust_id, status=OrderStatus.DELIVERED.value,
            payment_method=PaymentMethod.CARD.value, payment_status=PaymentStatus.PAID.value,
            subtotal=900000, discount_total=0, shipping_fee=0, total=900000, paid_amount=900000, refunded_amount=0,
            placed_at=clock.now() - timedelta(days=5), delivered_at=clock.now() - timedelta(days=3),
        )
    )
    item = OrderItemModel(id=uuid.uuid4(), order_id=order_id, variant_id=var.id, qty=1, unit_price=900000, allocated_discount=0, returned_qty=0)
    session.add(item)
    await session.commit()

    customer = Principal.authenticated_customer(customer_id=cust_id)
    inspector = Principal.staff(user_id=inspector_id, role=PrincipalRole.AGENT)
    approver = Principal.staff(user_id=approver_id, role=PrincipalRole.AGENT)

    proposal = await ReturnService(session).propose_return(
        principal=customer, conversation_id=uuid.uuid4(), order_code="SL-BIG001",
        items=[{"item_id": str(item.id), "qty": 1}], reason_code=ReturnReason.DEFECTIVE.value, resolution=ReturnResolution.REFUND.value,
    )
    confirmed = await ActionService(session).confirm_action(principal=customer, action_id=uuid.UUID(proposal["action_id"]), preview_hash=proposal["preview_hash"])
    return_code = confirmed["return_code"]
    ret_before = await ReturnRepository(session).get_by_code(return_code)
    assert ret_before is not None
    await add_evidence(session, ret_before.id, photos=2)
    for gate_a in await ApprovalRepository(session).list_pending():
        await ApprovalService(session).decide_approval(principal=approver, approval_id=gate_a.id, decision="approved", note="Ảnh hợp lệ")

    warehouse = WarehouseService(session)
    with pytest.raises(ConflictError):  # nothing to inspect before the parcel arrives
        await warehouse.inspect_return(principal=inspector, return_code=return_code, items_result=[])
    await warehouse.receive_shipment(principal=inspector, return_code=return_code)
    result = await warehouse.inspect_return(principal=inspector, return_code=return_code, items_result=[])
    await session.commit()
    assert result["needs_approval"] is True and result["refund_amount"] == 900000
    with pytest.raises(ConflictError):  # a second inspection would create a second refund
        await warehouse.inspect_return(principal=inspector, return_code=return_code, items_result=[])

    (gate_b,) = await ApprovalRepository(session).list_pending()
    with pytest.raises(ForbiddenError):  # the inspector raised the request and may not approve it
        await ApprovalService(session).decide_approval(principal=inspector, approval_id=gate_b.id, decision="approved", note="tự duyệt")
    await ApprovalService(session).decide_approval(principal=approver, approval_id=gate_b.id, decision="approved", note="Đã xem kết quả kiểm")
    await session.commit()

    ret = await ReturnRepository(session).get_by_code(return_code)
    assert ret is not None and ret.status == ReturnStatus.ACCEPTED.value
    refund = await RefundRepository(session).get_by_code(result["refund_code"])
    assert refund is not None and refund.status == RefundStatus.APPROVED.value
