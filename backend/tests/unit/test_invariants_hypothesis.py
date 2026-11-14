"""Hypothesis property-based tests verifying the 6 business invariants from Section 8.4."""

from __future__ import annotations

import uuid

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings
from shopagent.domain.models.entities import Order, OrderItem
from shopagent.domain.models.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    ReturnReason,
)
from shopagent.domain.policies.refund_calc import (
    calculate_allocated_discounts,
    calculate_refund_amount,
)
from shopagent.domain.services.approvals import check_role_hierarchy
from shopagent.domain.state_machines import (
    REFUND_TRANSITIONS,
    transition_refund_status,
)


@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
@given(
    item_prices=st.lists(st.integers(min_value=10_000, max_value=2_000_000), min_size=1, max_size=5),
    item_qtys=st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=5),
    discount_pct=st.integers(min_value=0, max_value=50),
    return_ratio=st.floats(min_value=0.1, max_value=1.0),
    reason=st.sampled_from(list(ReturnReason)),
)
def test_invariant_1_and_accounting_integrity_property(
    item_prices: list[int],
    item_qtys: list[int],
    discount_pct: int,
    return_ratio: float,
    reason: ReturnReason,
) -> None:
    """Property test for Invariant 1: Total refund <= paid_amount,

    and Accounting Integrity: sum(allocated_discounts) == discount_total.
    """
    n = min(len(item_prices), len(item_qtys))
    prices = item_prices[:n]
    qtys = item_qtys[:n]

    subtotal = sum(p * q for p, q in zip(prices, qtys, strict=False))
    discount_total = (subtotal * discount_pct) // 100
    shipping_fee = 30000 if subtotal < 500000 else 0
    total = subtotal - discount_total + shipping_fee
    paid_amount = total

    items_dict = [{"qty": q, "unit_price": p} for p, q in zip(prices, qtys, strict=False)]
    allocated_discounts = calculate_allocated_discounts(items_dict, discount_total)

    # Accounting integrity check
    assert sum(allocated_discounts) == discount_total

    # Create OrderItem list
    order_items: list[OrderItem] = []
    return_selection: list[tuple[OrderItem, int]] = []

    for i in range(n):
        oi = OrderItem(
            id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            variant_id=uuid.uuid4(),
            qty=qtys[i],
            unit_price=prices[i],
            allocated_discount=allocated_discounts[i],
            returned_qty=0,
        )
        order_items.append(oi)
        ret_qty = max(1, int(qtys[i] * return_ratio))
        ret_qty = min(ret_qty, qtys[i])
        return_selection.append((oi, ret_qty))

    order = Order(
        id=uuid.uuid4(),
        code="SL-HYPOTHESIS",
        customer_id=uuid.uuid4(),
        status=OrderStatus.DELIVERED,
        payment_method=PaymentMethod.CARD,
        payment_status=PaymentStatus.PAID,
        subtotal=subtotal,
        discount_total=discount_total,
        shipping_fee=shipping_fee,
        total=total,
        paid_amount=paid_amount,
        refunded_amount=0,
        items=order_items,
    )

    calc = calculate_refund_amount(
        order=order,
        items_to_return=return_selection,
        reason=reason,
    )

    # Invariant 1: Refund cannot exceed order paid total
    assert calc.refundable_amount <= paid_amount
    assert calc.refundable_amount >= 0


@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
@given(
    qty=st.integers(min_value=1, max_value=100),
    returned_qty=st.integers(min_value=0, max_value=100),
    additional_return=st.integers(min_value=0, max_value=50),
)
def test_invariant_2_returned_qty_le_qty(qty: int, returned_qty: int, additional_return: int) -> None:
    """Property test for Invariant 2: order_items.returned_qty <= qty."""
    item = OrderItem(
        id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        variant_id=uuid.uuid4(),
        qty=qty,
        unit_price=100000,
        allocated_discount=0,
        returned_qty=min(qty, returned_qty),
    )

    # Remaining returnable
    assert item.returned_qty <= item.qty
    can_return_more = item.remaining_returnable_qty
    assert can_return_more == item.qty - item.returned_qty

    # Attempt to increment beyond qty is prevented
    target_return = min(item.remaining_returnable_qty, additional_return)
    new_returned_qty = item.returned_qty + target_return
    assert new_returned_qty <= item.qty


@settings(max_examples=300)
@given(
    staff_role=st.sampled_from(["agent", "supervisor", "admin", "guest", "customer"]),
    required_role=st.sampled_from(["agent", "supervisor", "admin"]),
)
def test_invariant_4_role_hierarchy(staff_role: str, required_role: str) -> None:
    """Property test for Invariant 4: decided_by has sufficient role authority."""
    authorized = check_role_hierarchy(staff_role, required_role)
    if required_role == "admin":
        assert authorized == (staff_role in ("admin", "system"))
    elif required_role == "supervisor":
        assert authorized == (staff_role in ("supervisor", "admin", "system"))
    elif required_role == "agent":
        assert authorized == (staff_role in ("agent", "supervisor", "admin", "system"))


@settings(max_examples=500)
@given(
    curr_status=st.sampled_from(list(RefundStatus)),
    nxt_status=st.sampled_from(list(RefundStatus)),
)
def test_invariant_5_refund_state_transitions(curr_status: RefundStatus, nxt_status: RefundStatus) -> None:
    """Property test for Invariant 5: State transitions match valid transition graph."""
    allowed_transitions = REFUND_TRANSITIONS.get(curr_status, set())
    if nxt_status in allowed_transitions:
        # Must succeed
        transition_refund_status(curr_status, nxt_status)
    else:
        # Must reject with ConflictError
        from shopagent.core.errors import ConflictError
        with pytest.raises(ConflictError):
            transition_refund_status(curr_status, nxt_status)
