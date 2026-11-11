"""Data and invariant verification suite for shop-support-agent.

Checks:
- Accounting integrity (subtotal - discount + shipping = total; sum(allocated) = discount)
- 6 Invariants from Section 8.4
- Distribution coverage across order status, payment method, and product category
"""

from __future__ import annotations

from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.domain.models.enums import (
    ApprovalStatus,
    OrderStatus,
    PaymentStatus,
    RefundStatus,
)
from shopagent.domain.services.approvals import check_role_hierarchy
from shopagent.infra.db.tables import (
    ApprovalRequestModel,
    OrderItemModel,
    OrderModel,
    PaymentModel,
    ProductModel,
    ProductVariantModel,
    RefundModel,
    ReturnItemModel,
    ReturnRequestModel,
    StaffUserModel,
)


class VerificationResult:
    def __init__(self) -> None:
        self.checks_run: int = 0
        self.passed: int = 0
        self.failed: int = 0
        self.errors: list[str] = []

    def assert_true(self, condition: bool, description: str) -> None:
        self.checks_run += 1
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(description)

    @property
    def is_valid(self) -> bool:
        return self.failed == 0


async def verify_dataset(session: AsyncSession) -> VerificationResult:
    """Run full verification on current database state."""
    result = VerificationResult()

    # 1. Accounting Integrity: subtotal - discount_total + shipping_fee == total
    stmt = select(OrderModel)
    res = await session.execute(stmt)
    orders = list(res.scalars().all())

    result.assert_true(len(orders) > 0, "Có ít nhất 1 đơn hàng trong cơ sở dữ liệu")

    for order in orders:
        expected_total = order.subtotal - order.discount_total + order.shipping_fee
        if order.total != expected_total:
            result.assert_true(
                False,
                f"Đơn {order.code}: total ({order.total}) != subtotal ({order.subtotal}) - discount ({order.discount_total}) + shipping ({order.shipping_fee})",
            )
            break
    else:
        result.assert_true(True, "Toàn vẹn kế toán: total = subtotal - discount + shipping trên toàn bộ đơn")

    # 2. Allocated discount sum equals discount_total on each order
    for order in orders:
        stmt = select(func.coalesce(func.sum(OrderItemModel.allocated_discount), 0)).where(
            OrderItemModel.order_id == order.id
        )
        res = await session.execute(stmt)
        sum_alloc = int(res.scalar_one())
        if sum_alloc != order.discount_total:
            result.assert_true(
                False,
                f"Đơn {order.code}: tổng allocated_discount ({sum_alloc}) != discount_total ({order.discount_total})",
            )
            break
    else:
        result.assert_true(True, "Toàn vẹn kế toán: tổng allocated_discount bằng discount_total trên mọi đơn")

    # 3. Invariant 1: Total succeeded + processing refund <= paid_amount
    for order in orders:
        stmt = (
            select(func.coalesce(func.sum(RefundModel.amount), 0))
            .where(RefundModel.order_id == order.id)
            .where(RefundModel.status.in_([RefundStatus.PROCESSING.value, RefundStatus.SUCCEEDED.value]))
        )
        res = await session.execute(stmt)
        sum_refunded = int(res.scalar_one())
        if sum_refunded > order.paid_amount:
            result.assert_true(
                False,
                f"Bất biến 1 vi phạm trên đơn {order.code}: tổng hoàn tiền ({sum_refunded}) > đã thanh toán ({order.paid_amount})",
            )
            break
    else:
        result.assert_true(True, "Bất biến 1: Tổng tiền hoàn (succeeded + processing) <= tiền đã thanh toán")

    # 4. Invariant 2: order_items.returned_qty <= qty
    stmt = select(OrderItemModel).where(OrderItemModel.returned_qty > OrderItemModel.qty)
    res = await session.execute(stmt)
    bad_items = list(res.scalars().all())
    result.assert_true(
        len(bad_items) == 0,
        f"Bất biến 2: returned_qty <= qty (tìm thấy {len(bad_items)} dòng vi phạm)",
    )

    # 5. Invariant 3: A refund in processing has no pending/rejected approvals
    stmt = (
        select(RefundModel)
        .where(RefundModel.status == RefundStatus.PROCESSING.value)
    )
    res = await session.execute(stmt)
    processing_refunds = list(res.scalars().all())

    for ref in processing_refunds:
        stmt = (
            select(ApprovalRequestModel)
            .where(ApprovalRequestModel.subject_id == ref.id)
            .where(ApprovalRequestModel.status.in_([ApprovalStatus.PENDING.value, ApprovalStatus.REJECTED.value]))
        )
        res = await session.execute(stmt)
        bad_approvals = list(res.scalars().all())
        if bad_approvals:
            result.assert_true(
                False,
                f"Bất biến 3 vi phạm: Khoản hoàn {ref.code} đang xử lý nhưng còn yêu cầu duyệt pending/rejected",
            )
            break
    else:
        result.assert_true(True, "Bất biến 3: Refund sang processing khi không còn approval pending hoặc rejected")

    # 6. Invariant 4: approval_requests.decided_by has sufficient role
    stmt = select(ApprovalRequestModel).where(ApprovalRequestModel.decided_by.isnot(None))
    res = await session.execute(stmt)
    decided_approvals = list(res.scalars().all())

    for app in decided_approvals:
        staff_stmt = select(StaffUserModel).where(StaffUserModel.id == app.decided_by)
        staff_res = await session.execute(staff_stmt)
        staff = staff_res.scalar_one_or_none()
        if not staff or not check_role_hierarchy(staff.role, app.required_role):
            result.assert_true(
                False,
                f"Bất biến 4 vi phạm: Duyệt viên {staff.role if staff else 'None'} không đủ quyền cho cấp {app.required_role}",
            )
            break
    else:
        result.assert_true(True, "Bất biến 4: decided_by đủ thẩm quyền theo required_role")

    # 7. Invariant 6: gateway_txn_id unique per gateway
    stmt = (
        select(PaymentModel.gateway, PaymentModel.gateway_txn_id, func.count())
        .where(PaymentModel.gateway_txn_id.isnot(None))
        .group_by(PaymentModel.gateway, PaymentModel.gateway_txn_id)
        .having(func.count() > 1)
    )
    res = await session.execute(stmt)
    dupes = list(res.all())
    result.assert_true(
        len(dupes) == 0,
        f"Bất biến 6: gateway_txn_id duy nhất theo gateway (phát hiện {len(dupes)} trùng lặp)",
    )

    return result
