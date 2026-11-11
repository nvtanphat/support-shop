"""Warehouse receipt and return inspection domain service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.core.config import get_rules_config
from shopagent.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shopagent.core.ids import generate_uuid
from shopagent.core.principal import Principal, PrincipalRole
from shopagent.domain.models.entities import Customer, Order, OrderItem
from shopagent.domain.models.enums import (
    ApprovalGate,
    ApprovalStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ReturnReason,
    ReturnResolution,
    ReturnStatus,
)
from shopagent.domain.policies.engine import determine_refund_approval
from shopagent.domain.policies.refund_calc import calculate_refund_amount
from shopagent.domain.policies.risk import evaluate_risk_flags
from shopagent.domain.policies.rules import PolicyRules
from shopagent.domain.services.refunds import RefundService
from shopagent.domain.state_machines import transition_return_status
from shopagent.infra.db.repositories.approval_repo import ApprovalRepository
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.order_repo import OrderRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.repositories.return_repo import ReturnRepository
from shopagent.infra.db.tables import ApprovalRequestModel, ReturnRequestModel


class WarehouseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.return_repo = ReturnRepository(session)
        self.order_repo = OrderRepository(session)
        self.approval_repo = ApprovalRepository(session)
        self.audit_repo = AuditRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.refund_service = RefundService(session)
        self.clock = get_clock()

    async def receive_shipment(
        self,
        principal: Principal,
        return_code: str,
        tracking_number: str | None = None,
    ) -> ReturnRequestModel:
        """Mark shipment received at warehouse."""
        if not principal.is_staff and principal.role != PrincipalRole.SYSTEM:
            raise ForbiddenError("Chỉ nhân viên kho mới có thể tiếp nhận bưu kiện hoàn trả.")

        return_req = await self.return_repo.get_by_code(return_code)
        if not return_req:
            raise NotFoundError(f"Không tìm thấy yêu cầu trả hàng '{return_code}'.", error_code="RETURN_NOT_FOUND")

        prev_status = return_req.status
        transition_return_status(return_req, ReturnStatus.RECEIVED.value)
        return_req.received_at = self.clock.now()
        await self.return_repo.save(return_req)

        await self.audit_repo.log(
            actor_type="staff",
            actor_id=str(principal.user_id or "system"),
            action="return.received",
            subject_type="return_request",
            subject_id=str(return_req.id),
            before_state={"status": prev_status},
            after_state={"status": return_req.status, "tracking_number": tracking_number},
        )

        await self.outbox_repo.add_event(
            event_type="return.received",
            payload={
                "return_id": str(return_req.id),
                "return_code": return_req.code,
                "tracking_number": tracking_number,
            },
            idempotency_key=f"return_received_{return_req.id}",
        )

        return return_req

    def _to_domain_order(self, o: OrderModel) -> Order:
        items = [
            OrderItem(
                id=it.id,
                order_id=o.id,
                variant_id=it.variant_id,
                qty=it.qty,
                unit_price=it.unit_price,
                allocated_discount=it.allocated_discount,
                returned_qty=it.returned_qty,
                exchanged=it.exchanged,
            )
            for it in o.items
        ]
        return Order(
            id=o.id,
            code=o.code,
            customer_id=o.customer_id,
            status=OrderStatus(o.status),
            payment_method=PaymentMethod(o.payment_method),
            payment_status=PaymentStatus(o.payment_status),
            subtotal=o.subtotal,
            discount_total=o.discount_total,
            shipping_fee=o.shipping_fee,
            total=o.total,
            paid_amount=getattr(o, "paid_amount", o.total),
            refunded_amount=getattr(o, "refunded_amount", 0),
            channel=o.channel,
            note=o.note,
            policy_version=o.policy_version,
            placed_at=o.placed_at,
            delivered_at=o.delivered_at,
            items=items,
        )

    async def inspect_return(
        self,
        principal: Principal,
        return_code: str,
        items_result: list[dict[str, Any]],  # [{"item_id": uuid, "passed": bool, "notes": str}]
        staff_notes: str | None = None,
    ) -> dict[str, Any]:
        """Perform physical inspection on returned items at warehouse."""
        if not principal.is_staff and principal.role != PrincipalRole.SYSTEM:
            raise ForbiddenError("Chỉ nhân viên kho mới có thể kiểm định hàng trả.")

        return_req = await self.return_repo.get_by_code(return_code)
        if not return_req:
            raise NotFoundError(f"Không tìm thấy yêu cầu trả hàng '{return_code}'.", error_code="RETURN_NOT_FOUND")

        order = await self.order_repo.get_by_id(return_req.order_id)
        if not order:
            raise NotFoundError(f"Không tìm thấy đơn hàng của yêu cầu trả hàng.", error_code="ORDER_NOT_FOUND")

        all_passed = True
        result_map = {str(it["item_id"]): it for it in items_result}

        for ret_item in return_req.items:
            it_info = result_map.get(str(ret_item.order_item_id)) or result_map.get(str(ret_item.id))
            if it_info:
                passed = it_info.get("passed", True)
                ret_item.inspection_result = "passed" if passed else "failed"
                ret_item.inspection_note = it_info.get("notes")
                if not passed:
                    all_passed = False
            else:
                ret_item.inspection_result = "passed"

        now = self.clock.now()
        rules = PolicyRules.model_validate(get_rules_config())

        domain_order = self._to_domain_order(order)
        item_domain_map = {it.id: it for it in domain_order.items}

        # Determine refund calculation
        selected_items_calc: list[tuple[OrderItem, int]] = []
        for ri in return_req.items:
            dom_it = item_domain_map.get(ri.order_item_id)
            if dom_it:
                selected_items_calc.append((dom_it, ri.qty))

        calc_result = calculate_refund_amount(
            order=domain_order,
            items_to_return=selected_items_calc,
            reason=ReturnReason(return_req.reason_code),
        )

        breakdown_dict = {
            "refundable_amount": calc_result.refundable_amount,
            "items_subtotal": calc_result.items_subtotal,
            "shipping_fee_deduction": calc_result.shipping_fee_deduction,
            "items": [
                {
                    "sku": b.sku,
                    "qty": b.qty,
                    "unit_price": b.unit_price,
                    "gross": b.gross_amount,
                    "allocated_discount": b.allocated_discount,
                    "net": b.net_refundable,
                }
                for b in calc_result.items_breakdown
            ],
        }

        # Gate B approval check
        flags = list(return_req.risk_flags or [])
        if not all_passed:
            flags.append("condition_issue")

        gate, required_role = determine_refund_approval(
            amount=calc_result.refundable_amount,
            risk_flags=flags,
            policy=rules,
        )

        prev_status = return_req.status
        needs_gate_b_approval = required_role != "auto"

        if needs_gate_b_approval:
            # Create Gate B approval request
            approval = ApprovalRequestModel(
                id=generate_uuid(),
                subject_type="refund",
                subject_id=return_req.id,
                gate=gate.value if hasattr(gate, "value") else str(gate),
                required_role=required_role,
                status=ApprovalStatus.PENDING.value,
                requested_at=now,
                note=f"Kiểm hàng hoàn trả: {staff_notes or 'Cần duyệt trước khi giải ngân'}.",
            )
            await self.approval_repo.save(approval)

            # Create RefundModel in pending_approval
            refund = await self.refund_service.create_refund(
                order_id=order.id,
                amount=calc_result.refundable_amount,
                breakdown=breakdown_dict,
                return_id=return_req.id,
                method="original",
                needs_approval=True,
                actor_id=str(principal.user_id),
            )
            approval.subject_id = refund.id  # Link approval to the refund record
            await self.approval_repo.save(approval)

            msg = "Kiểm hàng hoàn tất. Khoản hoàn tiền cần cấp thẩm quyền phê duyệt trước khi giải ngân."
        else:
            # Transition return to accepted
            transition_return_status(return_req, ReturnStatus.ACCEPTED.value)
            # Create RefundModel in created (ready for auto disburse)
            refund = await self.refund_service.create_refund(
                order_id=order.id,
                amount=calc_result.refundable_amount,
                breakdown=breakdown_dict,
                return_id=return_req.id,
                method="original",
                needs_approval=False,
                actor_id=str(principal.user_id),
            )
            msg = "Kiểm hàng đạt chuẩn. Khoản hoàn tiền đã được tạo và sẵn sàng giải ngân tự động."

        await self.return_repo.save(return_req)

        await self.audit_repo.log(
            actor_type="staff",
            actor_id=str(principal.user_id or "system"),
            action="return.inspected",
            subject_type="return_request",
            subject_id=str(return_req.id),
            before_state={"status": prev_status},
            after_state={
                "status": return_req.status,
                "all_passed": all_passed,
                "refund_id": str(refund.id),
                "needs_approval": needs_gate_b_approval,
            },
        )

        await self.outbox_repo.add_event(
            event_type="return.inspected",
            payload={
                "return_id": str(return_req.id),
                "return_code": return_req.code,
                "all_passed": all_passed,
                "refund_id": str(refund.id),
                "refund_amount": refund.amount,
            },
            idempotency_key=f"return_inspected_{return_req.id}",
        )

        return {
            "return_code": return_req.code,
            "status": return_req.status,
            "all_passed": all_passed,
            "refund_code": refund.code,
            "refund_amount": refund.amount,
            "needs_approval": needs_gate_b_approval,
            "message": msg,
        }
