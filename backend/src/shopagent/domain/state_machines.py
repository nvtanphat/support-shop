"""State machine transitions and validators for orders, returns, and refunds."""

from __future__ import annotations

from typing import Any

from shopagent.core.errors import ConflictError
from shopagent.domain.models.enums import (
    ApprovalStatus,
    ConversationMode,
    OrderStatus,
    PendingActionStatus,
    RefundStatus,
    ReturnStatus,
)

ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING_PAYMENT: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PACKING, OrderStatus.CANCELLED},
    OrderStatus.PACKING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.DELIVERY_FAILED},
    OrderStatus.DELIVERY_FAILED: {OrderStatus.OUT_FOR_DELIVERY, OrderStatus.RETURNING_TO_SELLER},
    OrderStatus.RETURNING_TO_SELLER: {OrderStatus.RETURNED_TO_SELLER},
    OrderStatus.RETURNED_TO_SELLER: set(),
    OrderStatus.DELIVERED: {OrderStatus.COMPLETED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
}

RETURN_TRANSITIONS: dict[ReturnStatus, set[ReturnStatus]] = {
    ReturnStatus.REQUESTED: {ReturnStatus.PENDING_REVIEW, ReturnStatus.APPROVED, ReturnStatus.AWAITING_RETURN, ReturnStatus.REJECTED},
    ReturnStatus.PENDING_REVIEW: {ReturnStatus.APPROVED, ReturnStatus.AWAITING_RETURN, ReturnStatus.REJECTED},
    ReturnStatus.APPROVED: {ReturnStatus.AWAITING_RETURN},
    ReturnStatus.AWAITING_RETURN: {ReturnStatus.IN_TRANSIT_BACK, ReturnStatus.RECEIVED, ReturnStatus.EXPIRED},
    ReturnStatus.IN_TRANSIT_BACK: {ReturnStatus.RECEIVED},
    ReturnStatus.RECEIVED: {
        ReturnStatus.INSPECTING,
        ReturnStatus.ACCEPTED,
        ReturnStatus.PARTIALLY_ACCEPTED,
        ReturnStatus.REJECTED_AFTER_INSPECTION,
        ReturnStatus.COMPLETED,
    },
    ReturnStatus.INSPECTING: {
        ReturnStatus.ACCEPTED,
        ReturnStatus.PARTIALLY_ACCEPTED,
        ReturnStatus.REJECTED_AFTER_INSPECTION,
        ReturnStatus.COMPLETED,
    },
    ReturnStatus.ACCEPTED: {ReturnStatus.CLOSED, ReturnStatus.COMPLETED},
    ReturnStatus.PARTIALLY_ACCEPTED: {ReturnStatus.CLOSED, ReturnStatus.COMPLETED},
    ReturnStatus.REJECTED_AFTER_INSPECTION: {ReturnStatus.CLOSED},
    ReturnStatus.COMPLETED: {ReturnStatus.CLOSED},
    ReturnStatus.REJECTED: set(),
    ReturnStatus.EXPIRED: set(),
    ReturnStatus.CLOSED: set(),
}

REFUND_TRANSITIONS: dict[RefundStatus, set[RefundStatus]] = {
    RefundStatus.CREATED: {RefundStatus.PENDING_APPROVAL, RefundStatus.APPROVED, RefundStatus.PROCESSING, RefundStatus.REJECTED},
    RefundStatus.PENDING_APPROVAL: {RefundStatus.APPROVED, RefundStatus.REJECTED},
    RefundStatus.APPROVED: {RefundStatus.PROCESSING},
    RefundStatus.PROCESSING: {RefundStatus.SUCCEEDED, RefundStatus.FAILED},
    RefundStatus.SUCCEEDED: set(),
    RefundStatus.FAILED: {RefundStatus.PROCESSING, RefundStatus.REJECTED},  # Allow retry up to max attempts
    RefundStatus.REJECTED: set(),
}

APPROVAL_TRANSITIONS: dict[ApprovalStatus, set[ApprovalStatus]] = {
    ApprovalStatus.PENDING: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED},
    ApprovalStatus.APPROVED: set(),
    ApprovalStatus.REJECTED: set(),
}

PENDING_ACTION_TRANSITIONS: dict[PendingActionStatus, set[PendingActionStatus]] = {
    PendingActionStatus.PROPOSED: {
        PendingActionStatus.CONFIRMED,
        PendingActionStatus.CANCELLED,
        PendingActionStatus.EXPIRED,
        PendingActionStatus.FAILED,
    },
    PendingActionStatus.CONFIRMED: set(),
    PendingActionStatus.CANCELLED: set(),
    PendingActionStatus.EXPIRED: set(),
    PendingActionStatus.FAILED: set(),
}

CONVERSATION_MODE_TRANSITIONS: dict[ConversationMode, set[ConversationMode]] = {
    ConversationMode.AI: {ConversationMode.WAITING_HUMAN, ConversationMode.CLOSED},
    ConversationMode.WAITING_HUMAN: {ConversationMode.HUMAN, ConversationMode.AI, ConversationMode.CLOSED},
    ConversationMode.HUMAN: {ConversationMode.AI, ConversationMode.CLOSED},
    ConversationMode.CLOSED: {ConversationMode.AI},
}


def _normalize_and_validate(
    curr_val: Any,
    nxt_val: Any,
    enum_cls: type,
    transitions: dict[Any, set[Any]],
    entity_name: str,
) -> None:
    curr_attr = "mode" if hasattr(curr_val, "mode") else ("status" if hasattr(curr_val, "status") else None)
    is_model = curr_attr is not None
    raw_curr = getattr(curr_val, curr_attr) if is_model else curr_val

    curr_enum = enum_cls(raw_curr.value if hasattr(raw_curr, "value") else raw_curr)
    nxt_enum = enum_cls(nxt_val.value if hasattr(nxt_val, "value") else nxt_val)

    allowed = transitions.get(curr_enum, set())
    if nxt_enum not in allowed:
        raise ConflictError(
            f"Không thể chuyển trạng thái {entity_name} từ '{curr_enum.value}' sang '{nxt_enum.value}'.",
            error_code=f"INVALID_{entity_name.upper()}_STATE_TRANSITION",
        )
    if is_model:
        setattr(curr_val, curr_attr, nxt_enum.value)


def transition_order_status(curr: Any, nxt: Any) -> None:
    _normalize_and_validate(curr, nxt, OrderStatus, ORDER_TRANSITIONS, "đơn hàng")


def transition_return_status(curr: Any, nxt: Any) -> None:
    _normalize_and_validate(curr, nxt, ReturnStatus, RETURN_TRANSITIONS, "trả hàng")


def transition_refund_status(curr: Any, nxt: Any) -> None:
    _normalize_and_validate(curr, nxt, RefundStatus, REFUND_TRANSITIONS, "hoàn tiền")


def transition_approval_status(curr: Any, nxt: Any) -> None:
    _normalize_and_validate(curr, nxt, ApprovalStatus, APPROVAL_TRANSITIONS, "phê duyệt")


def transition_pending_action_status(curr: Any, nxt: Any) -> None:
    _normalize_and_validate(curr, nxt, PendingActionStatus, PENDING_ACTION_TRANSITIONS, "đề xuất")


def transition_conversation_mode(curr: Any, nxt: Any) -> None:
    _normalize_and_validate(curr, nxt, ConversationMode, CONVERSATION_MODE_TRANSITIONS, "hội thoại")
