"""Approval workflow domain service."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.core.errors import ConflictError, ForbiddenError, NotFoundError
from shopagent.core.principal import Principal, PrincipalRole
from shopagent.domain.models.enums import (
    ApprovalStatus,
    OrderStatus,
    RefundStatus,
    ReturnStatus,
)
from shopagent.domain.state_machines import (
    transition_approval_status,
    transition_order_status,
    transition_refund_status,
    transition_return_status,
)
from shopagent.infra.db.repositories.approval_repo import ApprovalRepository
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.order_repo import OrderRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.repositories.refund_repo import RefundRepository
from shopagent.infra.db.repositories.return_repo import ReturnRepository
from shopagent.infra.db.tables import ApprovalRequestModel


def check_role_hierarchy(staff_role: str, required_role: str) -> bool:
    """Validate Invariant 4: decided_by has sufficient role hierarchy."""
    role_weights = {
        "agent": 1,
        "supervisor": 2,
        "admin": 3,
        "system": 3,
    }
    staff_weight = role_weights.get(staff_role.lower(), 0)
    required_weight = role_weights.get(required_role.lower(), 1)
    return staff_weight >= required_weight


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.approval_repo = ApprovalRepository(session)
        self.order_repo = OrderRepository(session)
        self.return_repo = ReturnRepository(session)
        self.refund_repo = RefundRepository(session)
        self.audit_repo = AuditRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.clock = get_clock()

    async def list_pending(
        self,
        principal: Principal,
        required_role: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequestModel]:
        """List pending approvals accessible to staff principal."""
        if not principal.is_staff and principal.role != PrincipalRole.SYSTEM:
            raise ForbiddenError("Chỉ nhân viên mới có quyền xem danh sách phê duyệt.")
        return await self.approval_repo.list_pending(required_role=required_role, limit=limit)

    async def decide_approval(
        self,
        principal: Principal,
        approval_id: uuid.UUID,
        decision: str,  # "approved" or "rejected"
        note: str | None = None,
    ) -> ApprovalRequestModel:
        """Make an approval decision enforcing Invariant 4 & four-eyes principle."""
        if not principal.is_staff and principal.role != PrincipalRole.SYSTEM:
            raise ForbiddenError("Chỉ nhân viên mới có quyền thực hiện phê duyệt.", error_code="STAFF_REQUIRED")

        approval = await self.approval_repo.get_by_id(approval_id)
        if not approval:
            raise NotFoundError(f"Không tìm thấy yêu cầu phê duyệt {approval_id}.", error_code="APPROVAL_NOT_FOUND")

        if approval.status != ApprovalStatus.PENDING.value:
            raise ConflictError(
                f"Yêu cầu phê duyệt đã có kết quả ({approval.status}).",
                error_code="APPROVAL_ALREADY_DECIDED",
            )

        # Invariant 4: Role level validation
        actor_role = principal.role.value
        if not check_role_hierarchy(actor_role, approval.required_role):
            raise ForbiddenError(
                f"Vai trò '{actor_role}' không đủ thẩm quyền để duyệt yêu cầu cấp '{approval.required_role}'.",
                error_code="INSUFFICIENT_ROLE_AUTHORITY",
            )

        # Four-eyes principle: Staff who requested cannot approve their own request
        staff_id = principal.user_id
        if staff_id and getattr(approval, "requested_by", None) == staff_id:
            raise ForbiddenError(
                "Nguyên tắc bốn mắt (four-eyes): Người đề xuất không được tự phê duyệt yêu cầu của mình.",
                error_code="FOUR_EYES_VIOLATION",
            )

        now = self.clock.now()
        target_status = (
            ApprovalStatus.APPROVED.value if decision.lower() == "approved" else ApprovalStatus.REJECTED.value
        )
        prev_status = approval.status
        transition_approval_status(approval, target_status)
        approval.decided_by = staff_id
        approval.decided_at = now
        approval.note = note
        await self.approval_repo.save(approval)

        # Apply side-effects according to subject_type and gate
        if approval.subject_type == "return_request":
            return_req = await self.return_repo.get_by_id(approval.subject_id)
            if return_req:
                prev_return_status = return_req.status
                if target_status == ApprovalStatus.APPROVED.value:
                    transition_return_status(return_req, ReturnStatus.AWAITING_RETURN.value)
                else:
                    transition_return_status(return_req, ReturnStatus.REJECTED.value)
                await self.return_repo.save(return_req)

                await self.audit_repo.log(
                    actor_type="staff",
                    actor_id=str(staff_id or "system"),
                    action="return.approved" if target_status == ApprovalStatus.APPROVED.value else "return.rejected",
                    subject_type="return_request",
                    subject_id=str(return_req.id),
                    before_state={"status": prev_return_status},
                    after_state={"status": return_req.status, "approval_id": str(approval.id)},
                )

        elif approval.subject_type == "refund":
            refund = await self.refund_repo.get_by_id(approval.subject_id)
            if refund:
                prev_refund_status = refund.status
                if target_status == ApprovalStatus.APPROVED.value:
                    transition_refund_status(refund, RefundStatus.APPROVED.value)
                else:
                    transition_refund_status(refund, RefundStatus.REJECTED.value)
                refund.updated_at = now
                await self.refund_repo.save(refund)

                await self.audit_repo.log(
                    actor_type="staff",
                    actor_id=str(staff_id or "system"),
                    action="refund.approved" if target_status == ApprovalStatus.APPROVED.value else "refund.rejected",
                    subject_type="refund",
                    subject_id=str(refund.id),
                    before_state={"status": prev_refund_status},
                    after_state={"status": refund.status, "approval_id": str(approval.id)},
                )

        elif approval.subject_type == "cancellation":
            order = await self.order_repo.get_by_id(approval.subject_id)
            if order:
                prev_order_status = order.status
                if target_status == ApprovalStatus.APPROVED.value:
                    transition_order_status(order, OrderStatus.CANCELLED.value)
                    await self.order_repo.save(order)
                await self.audit_repo.log(
                    actor_type="staff",
                    actor_id=str(staff_id or "system"),
                    action="order.cancel_approved" if target_status == ApprovalStatus.APPROVED.value else "order.cancel_rejected",
                    subject_type="order",
                    subject_id=str(order.id),
                    before_state={"status": prev_order_status},
                    after_state={"status": order.status, "approval_id": str(approval.id)},
                )

        # Audit log for approval decision
        await self.audit_repo.log(
            actor_type="staff",
            actor_id=str(staff_id or "system"),
            action="approval.decided",
            subject_type="approval_request",
            subject_id=str(approval.id),
            before_state={"status": prev_status},
            after_state={
                "status": approval.status,
                "decided_by": str(approval.decided_by),
                "decision": target_status,
                "note": note,
            },
        )

        # Outbox event
        await self.outbox_repo.add_event(
            event_type="approval.decided",
            payload={
                "approval_id": str(approval.id),
                "subject_type": approval.subject_type,
                "subject_id": str(approval.subject_id),
                "decision": target_status,
                "decided_by": str(approval.decided_by),
            },
            idempotency_key=f"approval_decided_{approval.id}",
        )

        return approval
