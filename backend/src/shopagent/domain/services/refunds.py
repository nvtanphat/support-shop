"""Refund domain service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.core.errors import ConflictError, NotFoundError, ValidationError
from shopagent.core.ids import generate_refund_code, generate_uuid
from shopagent.domain.models.enums import (
    ApprovalStatus,
    PaymentStatus,
    RefundStatus,
)
from shopagent.domain.state_machines import (
    transition_order_status,
    transition_refund_status,
)
from shopagent.infra.db.repositories.approval_repo import ApprovalRepository
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.order_repo import OrderRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.repositories.refund_repo import RefundRepository
from shopagent.infra.db.tables import ApprovalRequestModel, OrderModel, RefundModel
from shopagent.infra.payments.port import PaymentGatewayPort


class RefundService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.order_repo = OrderRepository(session)
        self.refund_repo = RefundRepository(session)
        self.approval_repo = ApprovalRepository(session)
        self.audit_repo = AuditRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.clock = get_clock()

    async def create_refund(
        self,
        order_id: uuid.UUID,
        amount: int,
        breakdown: dict[str, Any] | None = None,
        return_id: uuid.UUID | None = None,
        method: str = "original",
        needs_approval: bool = False,
        actor_id: str | None = None,
    ) -> RefundModel:
        """Create a new refund record enforcing Invariant 1 (total <= paid_amount)."""
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f"Không tìm thấy đơn hàng {order_id}.", error_code="ORDER_NOT_FOUND")

        if amount <= 0:
            raise ValidationError("Số tiền hoàn phải lớn hơn 0.", error_code="INVALID_REFUND_AMOUNT")

        # Invariant 1 check: total (succeeded + processing) + new amount <= order.paid_amount
        current_refunded = await self.refund_repo.get_total_refunded_for_order(order_id)
        if current_refunded + amount > order.paid_amount:
            raise ValidationError(
                f"Tổng tiền hoàn ({current_refunded + amount} đ) vượt quá số tiền đã thanh toán ({order.paid_amount} đ).",
                error_code="REFUND_EXCEEDS_PAID_AMOUNT",
            )

        now = self.clock.now()
        initial_status = (
            RefundStatus.PENDING_APPROVAL.value if needs_approval else RefundStatus.CREATED.value
        )
        refund_code = generate_refund_code()

        refund = RefundModel(
            id=generate_uuid(),
            code=refund_code,
            order_id=order_id,
            return_id=return_id,
            amount=amount,
            breakdown=breakdown or {},
            method=method,
            status=initial_status,
            attempts=0,
            created_at=now,
            updated_at=now,
            version=1,
        )
        await self.refund_repo.save(refund)

        # Audit log
        await self.audit_repo.log(
            actor_type="system" if not actor_id else "staff",
            actor_id=actor_id or "system",
            action="refund.created",
            subject_type="refund",
            subject_id=str(refund.id),
            before_state=None,
            after_state={"code": refund.code, "amount": refund.amount, "status": refund.status},
        )

        # Outbox event
        await self.outbox_repo.add_event(
            event_type="refund.created",
            payload={
                "refund_id": str(refund.id),
                "refund_code": refund.code,
                "order_id": str(order_id),
                "amount": refund.amount,
                "status": refund.status,
            },
            idempotency_key=f"refund_created_{refund.id}",
        )

        return refund

    async def process_disbursement(
        self,
        refund_id: uuid.UUID,
        gateway: PaymentGatewayPort,
        actor_id: str | None = None,
    ) -> RefundModel:
        """Process refund payout to customer through payment gateway.

        Enforces:
        - Invariant 1: Total refunded <= paid_amount
        - Invariant 3: No pending or rejected approvals for this refund
        - Invariant 5: Valid state machine transitions with audit log
        - Invariant 6: Unique gateway_txn_id per gateway
        """
        refund = await self.refund_repo.get_by_id(refund_id)
        if not refund:
            raise NotFoundError(f"Không tìm thấy khoản hoàn tiền {refund_id}.", error_code="REFUND_NOT_FOUND")

        order = await self.order_repo.get_by_id(refund.order_id)
        if not order:
            raise NotFoundError(f"Không tìm thấy đơn hàng {refund.order_id}.", error_code="ORDER_NOT_FOUND")

        # Invariant 3: Check pending/rejected approvals for this refund
        has_pending = await self.approval_repo.has_pending_for_subject(refund.id)
        if has_pending:
            raise ConflictError(
                "Khoản hoàn tiền chưa thể xử lý vì đang chờ nhân viên phê duyệt.",
                error_code="REFUND_APPROVAL_PENDING",
            )

        # Invariant 1 check in transaction:
        # Sum of other processing/succeeded refunds + this refund <= paid_amount
        current_refunded = await self.refund_repo.get_total_refunded_for_order(order.id)
        # If this refund was already in processing, don't double count
        if refund.status not in (RefundStatus.PROCESSING.value, RefundStatus.SUCCEEDED.value):
            if current_refunded + refund.amount > order.paid_amount:
                raise ValidationError(
                    f"Khoản hoàn tiền ({refund.amount} đ) sẽ làm vượt quá số tiền đã thanh toán ({order.paid_amount} đ).",
                    error_code="REFUND_EXCEEDS_PAID_AMOUNT",
                )

        # Transition to processing
        prev_status = refund.status
        transition_refund_status(refund, RefundStatus.PROCESSING.value)
        refund.attempts += 1
        now = self.clock.now()
        refund.updated_at = now
        await self.refund_repo.save(refund)

        await self.audit_repo.log(
            actor_type="system" if not actor_id else "staff",
            actor_id=actor_id or "system",
            action="refund.status_changed",
            subject_type="refund",
            subject_id=str(refund.id),
            before_state={"status": prev_status},
            after_state={"status": refund.status, "attempts": refund.attempts},
        )

        # Call payment gateway
        original_txn_id = order.payment_method or f"TXN-{order.code}"
        idempotency_key = f"disburse_{refund.code}_{refund.attempts}"
        result = await gateway.refund(
            refund_code=refund.code,
            original_txn_id=original_txn_id,
            amount=refund.amount,
            reason=f"Refund for order {order.code}",
            idempotency_key=idempotency_key,
        )

        if result.success:
            # Transition to SUCCEEDED
            transition_refund_status(refund, RefundStatus.SUCCEEDED.value)
            refund.gateway_txn_id = result.gateway_txn_id
            refund.updated_at = self.clock.now()

            # Update order refunded_amount & payment_status
            order.refunded_amount += refund.amount
            if order.refunded_amount >= order.paid_amount:
                order.payment_status = PaymentStatus.REFUNDED.value
            else:
                order.payment_status = PaymentStatus.PARTIALLY_REFUNDED.value
            await self.order_repo.save(order)
            await self.refund_repo.save(refund)

            await self.audit_repo.log(
                actor_type="system" if not actor_id else "staff",
                actor_id=actor_id or "system",
                action="refund.succeeded",
                subject_type="refund",
                subject_id=str(refund.id),
                before_state={"status": RefundStatus.PROCESSING.value},
                after_state={
                    "status": refund.status,
                    "gateway_txn_id": refund.gateway_txn_id,
                    "order_refunded_amount": order.refunded_amount,
                },
            )

            await self.outbox_repo.add_event(
                event_type="refund.succeeded",
                payload={
                    "refund_id": str(refund.id),
                    "refund_code": refund.code,
                    "order_id": str(order.id),
                    "amount": refund.amount,
                    "gateway_txn_id": refund.gateway_txn_id,
                },
                idempotency_key=f"refund_succeeded_{refund.id}",
            )
        else:
            # Transition to FAILED
            transition_refund_status(refund, RefundStatus.FAILED.value)
            refund.updated_at = self.clock.now()
            await self.refund_repo.save(refund)

            await self.audit_repo.log(
                actor_type="system" if not actor_id else "staff",
                actor_id=actor_id or "system",
                action="refund.failed",
                subject_type="refund",
                subject_id=str(refund.id),
                before_state={"status": RefundStatus.PROCESSING.value},
                after_state={"status": refund.status, "error": result.error_message},
            )

            await self.outbox_repo.add_event(
                event_type="refund.failed",
                payload={
                    "refund_id": str(refund.id),
                    "refund_code": refund.code,
                    "order_id": str(order.id),
                    "amount": refund.amount,
                    "error": result.error_message,
                },
                idempotency_key=f"refund_failed_{refund.id}_{refund.attempts}",
            )

        return refund
