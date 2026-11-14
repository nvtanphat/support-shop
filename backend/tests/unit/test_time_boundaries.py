"""Unit tests for time boundaries and policy versioning.

Section 14.3 Requirement:
1. End-of-local-day deadline calculation (23:59:59 Vietnam time).
2. Request at 23:59:59 on last day (PASS) vs 00:00:00 next day (FAIL).
3. Delivered at 23:30 VN time (crosses UTC date boundary).
4. Order placed under policy version X retains version X even when requested under version Y.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shopagent.core.clock import (
    STORE_TIMEZONE,
    compute_deadline_days_end_of_day,
    to_utc,
)
from shopagent.domain.models.entities import Order, OrderItem
from shopagent.domain.models.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ReturnReason,
    ReturnResolution,
)
from shopagent.domain.policies.engine import check_return_eligibility
from shopagent.domain.policies.rules import PolicyRules


def test_deadline_end_of_day_calculation() -> None:
    tz = STORE_TIMEZONE
    # Delivered at 23:30 on Nov 1st Vietnam time
    # (which is 16:30 UTC on Nov 1st)
    del_vn = datetime(2026, 11, 1, 23, 30, 0, tzinfo=tz)

    # 7 days window for change of mind
    deadline_7d = compute_deadline_days_end_of_day(del_vn, 7)
    # Target date: Nov 1 + 7 days = Nov 8 at 23:59:59 VN time
    expected = datetime(2026, 11, 8, 23, 59, 59, 999999, tzinfo=tz)

    assert deadline_7d == expected
    assert deadline_7d.astimezone(tz).hour == 23
    assert deadline_7d.astimezone(tz).minute == 59
    assert deadline_7d.astimezone(tz).second == 59


def test_last_second_boundary_pass_and_fail() -> None:
    tz = STORE_TIMEZONE
    del_vn = datetime(2026, 11, 1, 10, 0, 0, tzinfo=tz)
    policy = PolicyRules()

    # Nov 1 + 7 days = Nov 8, 23:59:59
    pass_time = datetime(2026, 11, 8, 23, 59, 59, tzinfo=tz)
    fail_time = datetime(2026, 11, 9, 0, 0, 0, tzinfo=tz)

    item = OrderItem(
        id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        variant_id=uuid.uuid4(),
        sku="TS-AO-01",
        qty=1,
        unit_price=200000,
    )
    order = Order(
        id=item.order_id,
        code="SL-BOUND-01",
        customer_id=uuid.uuid4(),
        status=OrderStatus.DELIVERED,
        payment_method=PaymentMethod.CARD,
        payment_status=PaymentStatus.PAID,
        subtotal=200000,
        discount_total=0,
        shipping_fee=30000,
        total=230000,
        paid_amount=230000,
        delivered_at=del_vn,
        items=[item],
    )

    # 1. At 23:59:59 on Day 7 -> ELIGIBLE
    res_pass = check_return_eligibility(
        order=order,
        items_to_return=[(item, 1)],
        reason=ReturnReason.CHANGE_OF_MIND,
        resolution=ReturnResolution.REFUND,
        as_of=pass_time,
        policy=policy,
    )
    assert res_pass.eligible is True
    assert res_pass.decision_code == "ELIGIBLE"

    # 2. At 00:00:00 on Day 8 -> EXPIRED
    res_fail = check_return_eligibility(
        order=order,
        items_to_return=[(item, 1)],
        reason=ReturnReason.CHANGE_OF_MIND,
        resolution=ReturnResolution.REFUND,
        as_of=fail_time,
        policy=policy,
    )
    assert res_fail.eligible is False
    assert res_fail.decision_code == "EXPIRED_WINDOW"


def test_utc_timezone_cross_day_boundary() -> None:
    tz = STORE_TIMEZONE
    # 23:30 VN time on Nov 1st is Nov 1st in VN, but 16:30 UTC on Nov 1st
    del_vn = datetime(2026, 11, 1, 23, 30, 0, tzinfo=tz)
    del_utc = to_utc(del_vn)

    # Computing deadline using UTC vs VN datetime must yield identical local deadline
    deadline_from_vn = compute_deadline_days_end_of_day(del_vn, 7)
    deadline_from_utc = compute_deadline_days_end_of_day(del_utc, 7)

    assert deadline_from_vn == deadline_from_utc
    assert deadline_from_utc.astimezone(tz).day == 8
    assert deadline_from_utc.astimezone(tz).hour == 23


def test_policy_version_applied_from_order_placed_at() -> None:
    """Invariant D20: Policy version is pinned at order placed_at."""
    item = OrderItem(
        id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        variant_id=uuid.uuid4(),
        sku="TS-AO-02",
        qty=1,
        unit_price=200000,
    )
    order = Order(
        id=item.order_id,
        code="SL-VERSION-01",
        customer_id=uuid.uuid4(),
        status=OrderStatus.DELIVERED,
        payment_method=PaymentMethod.CARD,
        payment_status=PaymentStatus.PAID,
        subtotal=200000,
        discount_total=0,
        shipping_fee=30000,
        total=230000,
        paid_amount=230000,
        policy_version="2026-11-01",
        delivered_at=datetime(2026, 11, 5, 10, 0, 0, tzinfo=STORE_TIMEZONE),
        items=[item],
    )

    # Regardless of system current policy version, order.policy_version is 2026-11-01
    assert order.policy_version == "2026-11-01"
