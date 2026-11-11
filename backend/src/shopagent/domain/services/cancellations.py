"""Order cancellation domain service."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock, to_utc
from shopagent.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shopagent.core.ids import generate_action_code, generate_refund_code, generate_uuid
from shopagent.core.principal import Principal
from shopagent.core.security import compute_preview_hash
from shopagent.domain.models.enums import (
    ApprovalGate,
    ApprovalStatus,
    OrderStatus,
    PaymentStatus,
    PendingActionStatus,
    PendingActionType,
    RefundStatus,
)
from shopagent.domain.state_machines import transition_order_status
from shopagent.infra.db.repositories.action_repo import ActionRepository
from shopagent.infra.db.repositories.approval_repo import ApprovalRepository
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.order_repo import OrderRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.repositories.refund_repo import RefundRepository
from shopagent.infra.db.tables import ApprovalRequestModel, OrderModel, PendingActionModel, RefundModel


class CancellationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.order_repo = OrderRepository(session)
        self.action_repo = ActionRepository(session)
        self.approval_repo = ApprovalRepository(session)
        self.refund_repo = RefundRepository(session)
        self.audit_repo = AuditRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.clock = get_clock()

    async def propose_cancellation(
        self,
        principal: Principal,
        conversation_id: uuid.UUID,
        order_code: str,
        reason: str = "customer_request",
    ) -> dict[str, Any]:
        """Create a cancellation proposal for customer confirmation."""
        if not principal.is_authenticated_customer or principal.customer_id is None:
            raise ForbiddenError("Chỉ khách hàng sở hữu đơn mới có thể yêu cầu hủy đơn.")

        order = await self.order_repo.get_by_code(order_code)
        if not order:
            raise NotFoundError(f"Không tìm thấy đơn hàng '{order_code}'.", error_code="ORDER_NOT_FOUND")

        if order.customer_id != principal.customer_id:
            raise ForbiddenError("Bạn không có quyền hủy đơn hàng của khách hàng khác.", error_code="ORDER_ACCESS_DENIED")

        # Check cancellable status
        if order.status not in (
            OrderStatus.PENDING_PAYMENT.value,
            OrderStatus.CONFIRMED.value,
            OrderStatus.PACKING.value,
        ):
            raise ConflictError(
                f"Đơn hàng đang ở trạng thái '{order.status}', không thể hủy trực tiếp.",
                error_code="ORDER_NOT_CANCELLABLE",
                hint="Đơn hàng đã xuất kho hoặc đã giao. Vui lòng nhận hàng rồi làm thủ tục trả hàng nếu muốn hoàn tiền.",
            )

        needs_staff_approval = order.status == OrderStatus.PACKING.value

        payload = {
            "order_id": str(order.id),
            "order_code": order.code,
            "reason": reason,
            "needs_approval": needs_staff_approval,
            "total_refund": order.total if order.payment_status == PaymentStatus.PAID.value else 0,
        }
        payload_hash = compute_preview_hash(payload)

        # Check existing proposal
        existing = await self.action_repo.get_active_proposal(conversation_id, payload_hash)
        if existing and existing.expires_at > self.clock.now():
            return {
                "action_id": str(existing.id),
                "type": existing.type,
                "preview": existing.preview,
                "preview_hash": existing.payload_hash,
                "expires_at": existing.expires_at.isoformat(),
            }

        preview = {
            "title": f"Xác nhận hủy đơn hàng {order.code}",
            "order_code": order.code,
            "current_status": order.status,
            "needs_approval": needs_staff_approval,
            "refund_amount": order.total if order.payment_status == PaymentStatus.PAID.value else 0,
            "message": (
                "Đơn hàng đang đóng gói, yêu cầu hủy sẽ được chuyển nhân viên kho duyệt."
                if needs_staff_approval
                else "Đơn hàng sẽ được hủy ngay lập tức sau khi bạn bấm Xác nhận."
            ),
        }

        now = self.clock.now()
        action = PendingActionModel(
            id=generate_uuid(),
            conversation_id=conversation_id,
            customer_id=principal.customer_id,
            type=PendingActionType.CANCEL_ORDER.value,
            payload=payload,
            payload_hash=payload_hash,
            preview=preview,
            status=PendingActionStatus.PROPOSED.value,
            presented_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        await self.action_repo.save(action)

        return {
            "action_id": str(action.id),
            "type": action.type,
            "preview": preview,
            "preview_hash": payload_hash,
            "expires_at": action.expires_at.isoformat(),
        }

    async def execute_cancellation(
        self, principal: Principal, action: PendingActionModel, preview_hash: str
    ) -> dict[str, Any]:
        """Execute cancellation inside transaction after customer confirmed."""
        if action.payload_hash != preview_hash:
            raise ValidationError(
                "Mã băm điều khoản xem trước không khớp. Vui lòng kiểm tra lại điều khoản trước khi xác nhận.",
                error_code="PREVIEW_HASH_MISMATCH",
            )

        now = self.clock.now()
        if to_utc(action.expires_at) < to_utc(now):
            action.status = PendingActionStatus.EXPIRED.value
            await self.action_repo.save(action)
            raise ConflictError("Đề xuất đã hết thời hạn hiệu lực (30 phút).", error_code="ACTION_EXPIRED")

        order_id = uuid.UUID(action.payload["order_id"])
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError("Đơn hàng không tồn tại.", error_code="ORDER_NOT_FOUND")

        # Ownership check
        if order.customer_id != principal.customer_id:
            raise ForbiddenError("Bạn không phải chủ sở hữu đơn hàng này.", error_code="ORDER_ACCESS_DENIED")

        before_order_status = order.status

        # Re-check status in transaction
        if order.status in (OrderStatus.PENDING_PAYMENT.value, OrderStatus.CONFIRMED.value):
            transition_order_status(OrderStatus(order.status), OrderStatus.CANCELLED)
            order.status = OrderStatus.CANCELLED.value
            await self.order_repo.save(order)

            # Audit log
            await self.audit_repo.log(
                actor_type="customer",
                actor_id=str(principal.customer_id),
                action="order.cancel.self_service",
                subject_type="order",
                subject_id=str(order.id),
                before_state={"status": before_order_status},
                after_state={"status": order.status},
            )

            # If paid, generate full refund
            if order.payment_status == PaymentStatus.PAID.value:
                refund = RefundModel(
                    id=generate_uuid(),
                    code=generate_refund_code(),
                    order_id=order.id,
                    amount=order.total,
                    breakdown={"reason": "order_cancelled", "total": order.total},
                    method="original",
                    status=RefundStatus.APPROVED.value,  # Cancel before packing auto-approves refund
                )
                await self.refund_repo.save(refund)

                # Outbox event for worker to disburse
                await self.outbox_repo.add_event(
                    event_type="refund.disburse",
                    payload={"refund_id": str(refund.id), "order_id": str(order.id), "amount": order.total},
                    idempotency_key=f"disburse_{refund.id}",
                )

            action.status = PendingActionStatus.CONFIRMED.value
            action.result = {"status": "cancelled", "order_code": order.code}
            await self.action_repo.save(action)

            return {
                "success": True,
                "status": "cancelled",
                "order_code": order.code,
                "message": f"Đơn hàng {order.code} đã được hủy thành công.",
            }

        elif order.status == OrderStatus.PACKING.value:
            # Requires staff approval
            approval = ApprovalRequestModel(
                id=generate_uuid(),
                subject_type="cancellation",
                subject_id=order.id,
                gate=ApprovalGate.CANCEL_PACKING.value,
                required_role="agent",
                status=ApprovalStatus.PENDING.value,
                requested_at=now,
                note=action.payload.get("reason", "Khách yêu cầu hủy khi đơn đang đóng gói"),
            )
            await self.approval_repo.save(approval)

            action.status = PendingActionStatus.CONFIRMED.value
            action.result = {"status": "pending_approval", "order_code": order.code}
            await self.action_repo.save(action)

            await self.audit_repo.log(
                actor_type="customer",
                actor_id=str(principal.customer_id),
                action="order.cancel.request_approval",
                subject_type="order",
                subject_id=str(order.id),
                before_state={"status": before_order_status},
                after_state={"status": order.status, "approval_id": str(approval.id)},
            )

            return {
                "success": True,
                "status": "pending_approval",
                "order_code": order.code,
                "message": f"Yêu cầu hủy đơn hàng {order.code} đã được gửi tới nhân viên hỗ trợ để duyệt.",
            }

        else:
            action.status = PendingActionStatus.FAILED.value
            await self.action_repo.save(action)
            raise ConflictError(
                f"Đơn hàng đã chuyển sang trạng thái '{order.status}', không thể hủy.",
                error_code="ORDER_STATUS_CHANGED",
            )
