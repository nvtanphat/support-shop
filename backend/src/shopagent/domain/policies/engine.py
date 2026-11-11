"""Deterministic business policy engine for return/cancellation eligibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from shopagent.core.clock import compute_deadline_days_end_of_day
from shopagent.domain.models.entities import Order, OrderItem
from shopagent.domain.models.enums import (
    ApprovalGate,
    OrderStatus,
    ReturnFlag,
    ReturnReason,
    ReturnResolution,
)
from shopagent.domain.policies.refund_calc import (
    RefundCalculationResult,
    calculate_refund_amount,
)
from shopagent.domain.policies.rules import PolicyRules


@dataclass
class EligibilityResult:
    eligible: bool
    decision_code: str
    clause_id: str
    message: str
    requires_evidence: bool = False
    requires_video: bool = False
    min_photos: int = 0
    gate: ApprovalGate | None = None
    required_role: str = "agent"  # auto, agent, supervisor
    estimated_refund: RefundCalculationResult | None = None
    ship_back_deadline: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)


def check_return_eligibility(
    order: Order,
    items_to_return: list[tuple[OrderItem, int]],  # (order_item, return_qty)
    reason: ReturnReason,
    resolution: ReturnResolution,
    as_of: datetime,
    policy: PolicyRules,
    risk_flags: list[str] | None = None,
) -> EligibilityResult:
    """Pure function to determine return eligibility against policy rules.

    Zero I/O, deterministic, fully unit-testable.
    """
    flags = risk_flags or []

    # 1. Check order sales channel: marketplace orders cannot be returned here
    if order.channel == "marketplace":
        return EligibilityResult(
            eligible=False,
            decision_code="ORDER_FROM_MARKETPLACE",
            clause_id="POL-RETURN-06",
            message="Đơn hàng được mua qua sàn TMĐT (Shopee/TikTok). Vui lòng tạo yêu cầu trực tiếp trên ứng dụng của sàn.",
        )

    # 2. Check order delivery status
    if order.status != OrderStatus.DELIVERED and order.status != OrderStatus.COMPLETED:
        return EligibilityResult(
            eligible=False,
            decision_code="ORDER_NOT_DELIVERED",
            clause_id="POL-RETURN-01",
            message="Đơn hàng chưa ở trạng thái giao thành công, không thể tạo yêu cầu đổi trả.",
        )

    if order.delivered_at is None:
        return EligibilityResult(
            eligible=False,
            decision_code="MISSING_DELIVERY_TIME",
            clause_id="POL-RETURN-01",
            message="Không tìm thấy mốc thời gian giao hàng hợp lệ.",
        )

    # 3. Check items and returnable quantities
    if not items_to_return:
        return EligibilityResult(
            eligible=False,
            decision_code="NO_ITEMS_SELECTED",
            clause_id="POL-RETURN-01",
            message="Vui lòng chọn ít nhất một sản phẩm cần đổi trả.",
        )

    for item, qty in items_to_return:
        if qty <= 0:
            return EligibilityResult(
                eligible=False,
                decision_code="INVALID_QUANTITY",
                clause_id="POL-RETURN-01",
                message=f"Số lượng trả cho sản phẩm {item.sku} không hợp lệ.",
            )
        if qty > item.remaining_returnable_qty:
            return EligibilityResult(
                eligible=False,
                decision_code="ALREADY_RETURNED",
                clause_id="POL-RETURN-04",
                message=f"Sản phẩm {item.sku} chỉ còn {item.remaining_returnable_qty} sản phẩm có thể trả.",
            )
        if resolution == ReturnResolution.EXCHANGE and item.exchanged:
            return EligibilityResult(
                eligible=False,
                decision_code="EXCHANGE_LIMIT_REACHED",
                clause_id="POL-EXCHANGE-01",
                message=f"Sản phẩm {item.sku} đã từng được đổi hàng một lần. Mỗi sản phẩm chỉ được đổi một lần duy nhất.",
            )

    # 4. Check time window
    return_rules = policy.return_policy
    if reason == ReturnReason.CHANGE_OF_MIND:
        window_days = return_rules.windows_days.change_of_mind  # 7 days
        clause = "POL-RETURN-02"
    else:
        window_days = return_rules.windows_days.defect_like     # 15 days
        clause = "POL-RETURN-01"

    deadline = compute_deadline_days_end_of_day(order.delivered_at, window_days)
    if as_of > deadline:
        return EligibilityResult(
            eligible=False,
            decision_code="EXPIRED_WINDOW",
            clause_id=clause,
            message=f"Đã quá thời hạn đổi trả ({window_days} ngày kể từ khi nhận hàng). Hạn chót là {deadline.strftime('%d/%m/%Y %H:%M')}.",
        )

    # 5. Check category exclusion for CHANGE_OF_MIND
    if reason == ReturnReason.CHANGE_OF_MIND:
        for item, _ in items_to_return:
            for flag in item.return_flags:
                if flag.value in return_rules.change_of_mind_excluded_flags:
                    return EligibilityResult(
                        eligible=False,
                        decision_code="CATEGORY_EXCLUDED",
                        clause_id="POL-RETURN-03",
                        message=f"Sản phẩm {item.product_name} thuộc nhóm loại trừ (hàng giảm giá đặc biệt, đồ lót, mỹ phẩm mở niêm phong...) không áp dụng lý do đổi ý.",
                    )

    # 6. Check evidence requirements
    requires_evidence = reason.value in return_rules.evidence.required_for
    min_photos = return_rules.evidence.min_photos if requires_evidence else 0
    requires_video = reason.value in return_rules.evidence.video_required_for

    # 7. Calculate estimated refund if resolution is refund
    estimated_refund: RefundCalculationResult | None = None
    if resolution == ReturnResolution.REFUND:
        estimated_refund = calculate_refund_amount(
            order=order,
            items_to_return=items_to_return,
            reason=reason,
            customer_shipping_fee_vnd=return_rules.return_shipping.customer_fee_vnd,
        )

    # 8. Determine approval gate and required role
    # Gate A (Return request acceptance)
    gate = ApprovalGate.A_RETURN
    if reason == ReturnReason.CHANGE_OF_MIND and not flags:
        required_role = "auto"
    elif flags:
        required_role = "supervisor"
    elif requires_evidence:
        required_role = "agent"
    else:
        required_role = "auto"

    # Deadline to ship items back (5 days from now)
    ship_back_deadline = compute_deadline_days_end_of_day(
        as_of, return_rules.ship_back_deadline_days
    )

    return EligibilityResult(
        eligible=True,
        decision_code="ELIGIBLE",
        clause_id=clause,
        message="Yêu cầu đủ điều kiện theo chính sách cửa hàng.",
        requires_evidence=requires_evidence,
        requires_video=requires_video,
        min_photos=min_photos,
        gate=gate,
        required_role=required_role,
        estimated_refund=estimated_refund,
        ship_back_deadline=ship_back_deadline,
        details={
            "window_days": window_days,
            "deadline": deadline.isoformat(),
            "risk_flags": flags,
        },
    )


def determine_refund_approval(
    amount: int, risk_flags: list[str], policy: PolicyRules
) -> tuple[ApprovalGate, str]:
    """Gate B: Determine required approval role for refund disbursement.

    Returns (ApprovalGate.B_REFUND, required_role: 'auto' | 'agent' | 'supervisor')
    """
    ref_rules = policy.refund_policy
    if risk_flags:
        return ApprovalGate.B_REFUND, "supervisor"

    if amount <= ref_rules.auto_approve_max_vnd:  # <= 500,000 VND
        return ApprovalGate.B_REFUND, "auto"
    elif amount <= ref_rules.agent_approve_max_vnd:  # <= 2,000,000 VND
        return ApprovalGate.B_REFUND, "agent"
    else:
        return ApprovalGate.B_REFUND, "supervisor"
