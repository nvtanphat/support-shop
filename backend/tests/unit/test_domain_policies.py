"""Unit tests for domain policies, calculations, risk rules, and state machines."""

import uuid
from datetime import datetime, timedelta

import pytest
from shopagent.core.clock import STORE_TIMEZONE
from shopagent.core.errors import ConflictError
from shopagent.domain.models.entities import Order, OrderItem
from shopagent.domain.models.enums import (
    ApprovalGate,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductCategory,
    RefundStatus,
    ReturnFlag,
    ReturnReason,
    ReturnResolution,
    ReturnStatus,
)
from shopagent.domain.policies.engine import (
    check_return_eligibility,
    determine_refund_approval,
)
from shopagent.domain.policies.refund_calc import (
    calculate_allocated_discounts,
    calculate_refund_amount,
)
from shopagent.domain.policies.risk import evaluate_risk_flags
from shopagent.domain.policies.rules import PolicyRules
from shopagent.domain.state_machines import (
    transition_order_status,
    transition_refund_status,
    transition_return_status,
)


@pytest.fixture
def policy() -> PolicyRules:
    return PolicyRules()


@pytest.fixture
def sample_order() -> Order:
    order_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    delivered_at = datetime(2026, 11, 5, 14, 0, tzinfo=STORE_TIMEZONE)

    items = [
        OrderItem(
            id=uuid.uuid4(),
            order_id=order_id,
            variant_id=uuid.uuid4(),
            sku="TS-AO-M-TRANG",
            product_name="Áo thun trắng",
            qty=1,
            unit_price=300000,
            allocated_discount=0,
            returned_qty=0,
            category=ProductCategory.FASHION,
            return_flags=[],
        ),
        OrderItem(
            id=uuid.uuid4(),
            order_id=order_id,
            variant_id=uuid.uuid4(),
            sku="TS-VAY-S-DEN",
            product_name="Váy dạ hội đen",
            qty=1,
            unit_price=500000,
            allocated_discount=30000,
            returned_qty=0,
            category=ProductCategory.FASHION,
            return_flags=[],
        ),
        OrderItem(
            id=uuid.uuid4(),
            order_id=order_id,
            variant_id=uuid.uuid4(),
            sku="CS-SON-DO",
            product_name="Son môi dưỡng ẩm",
            qty=1,
            unit_price=200000,
            allocated_discount=0,
            returned_qty=0,
            category=ProductCategory.COSMETICS,
            return_flags=[ReturnFlag.SEALED_COSMETIC],
        ),
    ]

    return Order(
        id=order_id,
        code="SL-TEST01",
        customer_id=cust_id,
        status=OrderStatus.DELIVERED,
        payment_method=PaymentMethod.EWALLET,
        payment_status=PaymentStatus.PAID,
        subtotal=1000000,
        discount_total=30000,
        shipping_fee=30000,
        total=1000000,
        channel="web",
        delivered_at=delivered_at,
        items=items,
    )


def test_discount_allocation_proportional() -> None:
    items = [
        {"qty": 1, "unit_price": 300000},
        {"qty": 1, "unit_price": 500000},
        {"qty": 2, "unit_price": 100000},
    ]
    # Total value = 300k + 500k + 200k = 1,000,000. Voucher discount = 60,000
    allocated = calculate_allocated_discounts(items, order_discount_total=60000)
    assert allocated == [18000, 30000, 12000]
    assert sum(allocated) == 60000


def test_refund_amount_calculation_change_of_mind(sample_order: Order) -> None:
    # Returning the dress (unit_price 500k, allocated_discount 30k) with change_of_mind
    # Expected: 500k - 30k discount - 30k shipping fee = 440,000 VND
    dress_item = sample_order.items[1]
    res = calculate_refund_amount(
        order=sample_order,
        items_to_return=[(dress_item, 1)],
        reason=ReturnReason.CHANGE_OF_MIND,
        customer_shipping_fee_vnd=30000,
    )
    assert res.refundable_amount == 440000
    assert res.shipping_fee_deduction == 30000
    assert res.total_allocated_discount == 30000


def test_eligibility_change_of_mind_within_7_days(sample_order: Order, policy: PolicyRules) -> None:
    # Delivered on 2026-11-05. Current time: 2026-11-10 (day 5 -> eligible)
    now = datetime(2026, 11, 10, 10, 0, tzinfo=STORE_TIMEZONE)
    dress_item = sample_order.items[1]

    result = check_return_eligibility(
        order=sample_order,
        items_to_return=[(dress_item, 1)],
        reason=ReturnReason.CHANGE_OF_MIND,
        resolution=ReturnResolution.REFUND,
        as_of=now,
        policy=policy,
    )
    assert result.eligible is True
    assert result.decision_code == "ELIGIBLE"
    assert result.clause_id == "POL-RETURN-02"
    assert result.requires_evidence is False
    assert result.required_role == "auto"  # change of mind with no risk flags auto-approves


def test_eligibility_change_of_mind_excluded_category(sample_order: Order, policy: PolicyRules) -> None:
    # Item has sealed_cosmetic flag -> excluded for change of mind
    cosmetic_item = sample_order.items[2]
    now = datetime(2026, 11, 7, 10, 0, tzinfo=STORE_TIMEZONE)

    result = check_return_eligibility(
        order=sample_order,
        items_to_return=[(cosmetic_item, 1)],
        reason=ReturnReason.CHANGE_OF_MIND,
        resolution=ReturnResolution.REFUND,
        as_of=now,
        policy=policy,
    )
    assert result.eligible is False
    assert result.decision_code == "CATEGORY_EXCLUDED"
    assert result.clause_id == "POL-RETURN-03"


def test_eligibility_defect_requires_evidence(sample_order: Order, policy: PolicyRules) -> None:
    dress_item = sample_order.items[1]
    now = datetime(2026, 11, 15, 10, 0, tzinfo=STORE_TIMEZONE)  # Day 10 (<= 15 days)

    result = check_return_eligibility(
        order=sample_order,
        items_to_return=[(dress_item, 1)],
        reason=ReturnReason.DEFECTIVE,
        resolution=ReturnResolution.REFUND,
        as_of=now,
        policy=policy,
    )
    assert result.eligible is True
    assert result.requires_evidence is True
    assert result.min_photos == 2
    assert result.required_role == "agent"  # needs human agent to review evidence


def test_eligibility_expired_window(sample_order: Order, policy: PolicyRules) -> None:
    dress_item = sample_order.items[1]
    # Delivered on 2026-11-05. 7 days deadline is 2026-11-12 23:59:59.
    # Check at 2026-11-13 00:01:00
    now = datetime(2026, 11, 13, 0, 1, tzinfo=STORE_TIMEZONE)

    result = check_return_eligibility(
        order=sample_order,
        items_to_return=[(dress_item, 1)],
        reason=ReturnReason.CHANGE_OF_MIND,
        resolution=ReturnResolution.REFUND,
        as_of=now,
        policy=policy,
    )
    assert result.eligible is False
    assert result.decision_code == "EXPIRED_WINDOW"


def test_refund_approval_gate_thresholds(policy: PolicyRules) -> None:
    # <= 500,000 VND without risk flags -> auto
    gate, role = determine_refund_approval(450000, risk_flags=[], policy=policy)
    assert gate == ApprovalGate.B_REFUND
    assert role == "auto"

    # <= 2,000,000 VND without risk flags -> agent
    gate, role = determine_refund_approval(1500000, risk_flags=[], policy=policy)
    assert role == "agent"

    # > 2,000,000 VND -> supervisor
    gate, role = determine_refund_approval(2500000, risk_flags=[], policy=policy)
    assert role == "supervisor"

    # Has risk flags -> supervisor regardless of amount
    gate, role = determine_refund_approval(300000, risk_flags=["many_returns"], policy=policy)
    assert role == "supervisor"


def test_risk_flags_detection() -> None:
    now = datetime(2026, 11, 11, 10, 0, tzinfo=STORE_TIMEZONE)
    # New account (< 7 days) with order > 2,000,000
    cust_created = now - timedelta(days=3)
    flags = evaluate_risk_flags(
        customer_created_at=cust_created,
        order_total=2500000,
        recent_return_count_30d=1,
        recent_orders_count=2,
        recent_returned_orders_count=0,
        now=now,
    )
    assert "new_account_high_value" in flags

    # Many returns >= 3 in 30 days
    flags2 = evaluate_risk_flags(
        customer_created_at=now - timedelta(days=60),
        order_total=500000,
        recent_return_count_30d=3,
        recent_orders_count=4,
        recent_returned_orders_count=3,
        now=now,
    )
    assert "many_returns" in flags2
    assert "high_return_rate" in flags2


def test_state_machines_transitions() -> None:
    # Valid order transition
    transition_order_status(OrderStatus.PENDING_PAYMENT, OrderStatus.CONFIRMED)
    transition_order_status(OrderStatus.CONFIRMED, OrderStatus.CANCELLED)

    # Invalid order transition raises ConflictError
    with pytest.raises(ConflictError):
        transition_order_status(OrderStatus.DELIVERED, OrderStatus.CANCELLED)

    # Valid return transition
    transition_return_status(ReturnStatus.REQUESTED, ReturnStatus.APPROVED)
    transition_return_status(ReturnStatus.APPROVED, ReturnStatus.AWAITING_RETURN)

    # Invalid return transition raises ConflictError
    with pytest.raises(ConflictError):
        transition_return_status(ReturnStatus.REJECTED, ReturnStatus.APPROVED)

    # Refund transitions
    transition_refund_status(RefundStatus.CREATED, RefundStatus.APPROVED)
    transition_refund_status(RefundStatus.APPROVED, RefundStatus.PROCESSING)
    transition_refund_status(RefundStatus.PROCESSING, RefundStatus.SUCCEEDED)

    with pytest.raises(ConflictError):
        transition_refund_status(RefundStatus.SUCCEEDED, RefundStatus.CREATED)
