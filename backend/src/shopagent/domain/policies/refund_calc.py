"""Refund amount and discount allocation calculations (pure functions, no DB/I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shopagent.domain.models.entities import Order, OrderItem
from shopagent.domain.models.enums import ReturnReason


@dataclass
class ItemRefundBreakdown:
    order_item_id: str
    sku: str
    product_name: str
    qty: int
    unit_price: int
    gross_amount: int
    allocated_discount: int
    net_refundable: int


@dataclass
class RefundCalculationResult:
    refundable_amount: int
    items_subtotal: int
    total_allocated_discount: int
    shipping_fee_deduction: int
    items_breakdown: list[ItemRefundBreakdown]
    explanation: str
    details: dict[str, Any] = field(default_factory=dict)


def calculate_allocated_discounts(
    items: list[dict[str, Any]], order_discount_total: int
) -> list[int]:
    """Allocate order-level discount proportionally to each item line by gross value.

    All math is in integer VND with remainder distributed to the largest line.
    """
    if order_discount_total <= 0 or not items:
        return [0] * len(items)

    total_value = sum(it["qty"] * it["unit_price"] for it in items)
    if total_value <= 0:
        return [0] * len(items)

    allocated: list[int] = []
    current_sum = 0
    max_idx = 0
    max_val = -1

    for idx, it in enumerate(items):
        line_val = it["qty"] * it["unit_price"]
        if line_val > max_val:
            max_val = line_val
            max_idx = idx
        line_discount = int((line_val * order_discount_total) / total_value)
        allocated.append(line_discount)
        current_sum += line_discount

    # Distribute integer rounding remainder
    remainder = order_discount_total - current_sum
    if remainder != 0:
        allocated[max_idx] += remainder

    return allocated


def calculate_refund_amount(
    order: Order,
    items_to_return: list[tuple[OrderItem, int]],  # (order_item, qty_to_return)
    reason: ReturnReason,
    customer_shipping_fee_vnd: int = 30000,
) -> RefundCalculationResult:
    """Calculate refund amount with itemized breakdown and fee deduction.

    Formula per item:
      refundable = (unit_price * return_qty) - (allocated_discount * (return_qty / item.qty))
    If reason is CHANGE_OF_MIND:
      customer pays return shipping fee (deducted from refund, default 30,000 VND).
    Net refund cannot be negative, and total cannot exceed order paid total.
    """
    items_breakdown: list[ItemRefundBreakdown] = []
    total_gross = 0
    total_discount = 0

    for item, return_qty in items_to_return:
        if return_qty <= 0:
            continue
        line_gross = item.unit_price * return_qty
        # Proportion of allocated discount corresponding to returned quantity
        line_discount = int(item.allocated_discount * return_qty / item.qty) if item.qty > 0 else 0

        line_net = max(0, line_gross - line_discount)

        total_gross += line_gross
        total_discount += line_discount

        items_breakdown.append(
            ItemRefundBreakdown(
                order_item_id=str(item.id),
                sku=item.sku,
                product_name=item.product_name,
                qty=return_qty,
                unit_price=item.unit_price,
                gross_amount=line_gross,
                allocated_discount=line_discount,
                net_refundable=line_net,
            )
        )

    subtotal_net = max(0, total_gross - total_discount)

    # Return shipping fee deduction
    shipping_deduction = customer_shipping_fee_vnd if reason == ReturnReason.CHANGE_OF_MIND else 0

    final_amount = max(0, subtotal_net - shipping_deduction)

    # Invariant: cannot exceed order total paid
    if final_amount > order.total:
        final_amount = order.total

    explanation_parts: list[str] = [
        f"Tổng giá trị sản phẩm trả: {total_gross:,.0f} đ".replace(",", "."),
    ]
    if total_discount > 0:
        explanation_parts.append(
            f"Trừ giảm giá phân bổ: -{total_discount:,.0f} đ".replace(",", ".")
        )
    if shipping_deduction > 0:
        explanation_parts.append(
            f"Trừ phí vận chuyển chiều về (đổi ý): -{shipping_deduction:,.0f} đ".replace(",", ".")
        )
    explanation_parts.append(
        f"Khoản hoàn thực nhận: {final_amount:,.0f} đ".replace(",", ".")
    )

    return RefundCalculationResult(
        refundable_amount=final_amount,
        items_subtotal=total_gross,
        total_allocated_discount=total_discount,
        shipping_fee_deduction=shipping_deduction,
        items_breakdown=items_breakdown,
        explanation="; ".join(explanation_parts),
        details={
            "gross": total_gross,
            "discount": total_discount,
            "shipping_fee": shipping_deduction,
            "net": final_amount,
            "items": [
                {
                    "sku": b.sku,
                    "qty": b.qty,
                    "unit_price": b.unit_price,
                    "gross": b.gross_amount,
                    "discount": b.allocated_discount,
                    "net": b.net_refundable,
                }
                for b in items_breakdown
            ],
        },
    )
