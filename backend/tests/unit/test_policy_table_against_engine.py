"""Test that PolicyEngine agrees 100% with the ground truth decision table.

Section 14.3 Requirement:
evals/ground_truth/policy_decision_table.csv has ~120 rows handcrafted from docs/business-spec.md.
PolicyEngine running against this table MUST match 100%.
"""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from shopagent.core.clock import get_shop_timezone
from shopagent.domain.models.entities import Order, OrderItem
from shopagent.domain.models.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductCategory,
    ReturnFlag,
    ReturnReason,
    ReturnResolution,
)
from shopagent.domain.policies.engine import check_return_eligibility, determine_refund_approval
from shopagent.domain.policies.rules import PolicyRules


def test_ground_truth_decision_table_against_policy_engine() -> None:
    csv_path = Path("evals/ground_truth/policy_decision_table.csv")
    assert csv_path.exists(), f"Missing ground truth table at {csv_path}"

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) >= 120, f"Expected at least 120 rows, found {len(rows)}"

    policy = PolicyRules()
    tz = get_shop_timezone()
    base_time = datetime(2026, 11, 11, 10, 0, 0, tzinfo=tz)

    mismatches = []

    for r in rows:
        case_id = r["case_id"]
        flags_raw = json.loads(r["flags"])
        flags = [ReturnFlag(f) for f in flags_raw]
        reason = ReturnReason(r["reason"])
        status = OrderStatus(r["order_status"]) if r["order_status"] in [s.value for s in OrderStatus] else OrderStatus.DELIVERED
        payment_method = PaymentMethod(r["payment_method"])
        del_days = float(r["del_days_ago"])
        subtotal = int(r["order_subtotal"])
        discount = int(r["order_discount"])
        price = int(r["item_price"])
        qty = int(r["item_qty"])
        ship_fee = int(r["shipping_fee"])
        risk = r["risk_flag"]
        risk_flags = [risk] if risk != "none" else []

        expected_eligible = r["expected_eligible"].lower() == "true"
        expected_refund = int(r["expected_refund_amount"])
        expected_role = r["expected_required_role"]

        delivered_at = (base_time - timedelta(days=del_days)) if status == OrderStatus.DELIVERED else None
        placed_at = (delivered_at - timedelta(days=3)) if delivered_at else (base_time - timedelta(days=1))

        # Construct Order and OrderItem entities
        order_item_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        line_val = price * qty
        alloc_discount = int((line_val * discount) / subtotal) if subtotal > 0 else 0

        item = OrderItem(
            id=order_item_id,
            order_id=uuid.uuid4(),
            variant_id=variant_id,
            sku=f"SKU-{case_id}",
            product_name="Test Product",
            category=ProductCategory.FASHION,
            return_flags=flags,
            unit_price=price,
            qty=qty,
            allocated_discount=alloc_discount,
            returned_qty=0,
            exchanged=False,
        )

        order = Order(
            id=item.order_id,
            code=f"SL-{case_id}",
            customer_id=uuid.uuid4(),
            status=status,
            payment_method=payment_method,
            payment_status=PaymentStatus.PAID,
            subtotal=subtotal,
            discount_total=discount,
            shipping_fee=ship_fee,
            total=subtotal - discount + ship_fee,
            paid_amount=subtotal - discount + ship_fee,
            refunded_amount=0,
            channel="web",
            policy_version="2026-11-01",
            placed_at=placed_at,
            delivered_at=delivered_at,
            items=[item],
        )

        # Run engine
        res = check_return_eligibility(
            order=order,
            items_to_return=[(item, qty)],
            reason=reason,
            resolution=ReturnResolution.REFUND,
            as_of=base_time,
            policy=policy,
            risk_flags=risk_flags,
        )

        # Assert eligibility
        if res.eligible != expected_eligible:
            mismatches.append(f"{case_id}: eligible got {res.eligible}, expected {expected_eligible} ({res.decision_code})")
            continue

        if expected_eligible:
            # Check refund amount
            assert res.estimated_refund is not None
            actual_refund = res.estimated_refund.refundable_amount
            if actual_refund != expected_refund:
                mismatches.append(f"{case_id}: refund got {actual_refund}, expected {expected_refund}")

            # Check Gate B role
            _, actual_role = determine_refund_approval(actual_refund, risk_flags, policy)
            if actual_role != expected_role:
                mismatches.append(f"{case_id}: role got {actual_role}, expected {expected_role}")

    assert not mismatches, f"Mismatches found in {len(mismatches)} cases:\n" + "\n".join(mismatches[:10])
