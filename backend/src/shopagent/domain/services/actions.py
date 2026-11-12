"""Pending action confirmation and lifecycle service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock, to_utc
from shopagent.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shopagent.core.principal import Principal
from shopagent.domain.models.enums import PendingActionStatus, PendingActionType
from shopagent.domain.services.cancellations import CancellationService
from shopagent.domain.services.returns import ReturnService
from shopagent.infra.db.repositories.action_repo import ActionRepository
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.tables import PendingActionModel


class ActionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.action_repo = ActionRepository(session)
        self.audit_repo = AuditRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.clock = get_clock()

    async def get_by_id(self, action_id: uuid.UUID) -> PendingActionModel | None:
        return await self.action_repo.get_by_id(action_id)

    async def confirm_action(
        self,
        principal: Principal,
        action_id: uuid.UUID,
        preview_hash: str,
    ) -> dict[str, Any]:
        """Confirm a proposed pending action upon customer confirmation."""
        action = await self.action_repo.get_by_id(action_id)
        if not action:
            raise NotFoundError(f"Không tìm thấy đề xuất hành động {action_id}.", error_code="ACTION_NOT_FOUND")

        # Verify customer ownership
        if principal.is_authenticated_customer:
            if action.customer_id != principal.customer_id:
                raise ForbiddenError("Bạn không sở hữu đề xuất hành động này.", error_code="ACTION_ACCESS_DENIED")
        elif not principal.is_staff and principal.customer_id != action.customer_id:
            raise ForbiddenError("Bạn không có quyền thực hiện đề xuất này.", error_code="ACTION_ACCESS_DENIED")

        if action.status != PendingActionStatus.PROPOSED.value:
            raise ConflictError(
                f"Đề xuất không ở trạng thái chờ xác nhận (hiện tại: {action.status}).",
                error_code="ACTION_NOT_PROPOSED",
            )

        now = self.clock.now()
        if to_utc(action.expires_at) < to_utc(now):
            action.status = PendingActionStatus.EXPIRED.value
            await self.action_repo.save(action)
            raise ConflictError("Đề xuất đã hết hạn xác nhận (quá 30 phút).", error_code="ACTION_EXPIRED")

        if action.payload_hash != preview_hash:
            raise ValidationError(
                "Mã băm điều khoản xác nhận không khớp bản xem trước.",
                error_code="PREVIEW_HASH_MISMATCH",
            )

        # Dispatch based on action type
        if action.type == PendingActionType.CANCEL_ORDER.value:
            cancellation_service = CancellationService(self.session)
            result = await cancellation_service.execute_cancellation(principal, action, preview_hash)
        elif action.type in (PendingActionType.RETURN_REQUEST.value, "return_order", "exchange_order"):
            return_service = ReturnService(self.session)
            result = await return_service.execute_return(principal, action, preview_hash)
        else:
            raise ValidationError(f"Loại đề xuất '{action.type}' không được hỗ trợ.", error_code="UNSUPPORTED_ACTION_TYPE")

        return result

    async def cancel_action(
        self,
        principal: Principal,
        action_id: uuid.UUID,
        reason: str | None = None,
    ) -> PendingActionModel:
        """Cancel a pending action proposal."""
        action = await self.action_repo.get_by_id(action_id)
        if not action:
            raise NotFoundError(f"Không tìm thấy đề xuất hành động {action_id}.", error_code="ACTION_NOT_FOUND")

        if principal.is_authenticated_customer and action.customer_id != principal.customer_id:
            raise ForbiddenError("Bạn không sở hữu đề xuất hành động này.", error_code="ACTION_ACCESS_DENIED")

        if action.status != PendingActionStatus.PROPOSED.value:
            raise ConflictError(
                f"Không thể hủy đề xuất ở trạng thái '{action.status}'.",
                error_code="ACTION_NOT_CANCELLABLE",
            )

        action.status = PendingActionStatus.CANCELLED.value
        await self.action_repo.save(action)

        await self.audit_repo.log(
            actor_type="customer" if principal.is_authenticated_customer else "staff",
            actor_id=str(principal.customer_id or principal.user_id or "anonymous"),
            action="action.cancelled",
            subject_type="pending_action",
            subject_id=str(action.id),
            before_state={"status": PendingActionStatus.PROPOSED.value},
            after_state={"status": action.status, "reason": reason},
        )

        await self.outbox_repo.add_event(
            event_type="action.cancelled",
            payload={"action_id": str(action.id), "reason": reason},
            idempotency_key=f"action_cancelled_{action.id}",
        )

        return action

    async def expire_stale_actions(self) -> int:
        """Expire actions that have exceeded their TTL."""
        now = self.clock.now()
        stmt = (
            select(PendingActionModel)
            .where(PendingActionModel.status == PendingActionStatus.PROPOSED.value)
            .where(PendingActionModel.expires_at < now)
        )
        res = await self.session.execute(stmt)
        stale_actions = list(res.scalars().all())

        for act in stale_actions:
            act.status = PendingActionStatus.EXPIRED.value
            await self.audit_repo.log(
                actor_type="system",
                actor_id="system",
                action="action.expired",
                subject_type="pending_action",
                subject_id=str(act.id),
                before_state={"status": PendingActionStatus.PROPOSED.value},
                after_state={"status": act.status},
            )

        await self.session.flush()
        return len(stale_actions)
