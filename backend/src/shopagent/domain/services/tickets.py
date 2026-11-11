"""Escalation support ticket domain service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.core.errors import ConflictError, ForbiddenError, NotFoundError
from shopagent.core.ids import generate_ticket_code, generate_uuid
from shopagent.core.principal import Principal, PrincipalRole
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.conversation_repo import ConversationRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.repositories.ticket_repo import TicketRepository
from shopagent.infra.db.tables import TicketModel


class TicketService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ticket_repo = TicketRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.audit_repo = AuditRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.clock = get_clock()

    async def create_ticket(
        self,
        principal: Principal,
        conversation_id: uuid.UUID,
        reason_code: str,
        agent_summary: str,
        priority: str = "normal",
        context_data: dict[str, Any] | None = None,
    ) -> TicketModel:
        """Create a human escalation ticket and switch conversation mode."""
        now = self.clock.now()
        ticket = TicketModel(
            id=generate_uuid(),
            code=generate_ticket_code(),
            conversation_id=conversation_id,
            customer_id=principal.customer_id,
            reason_code=reason_code,
            priority=priority,
            status="open",
            agent_summary=agent_summary,
            context=context_data or {},
            created_at=now,
        )
        await self.ticket_repo.save(ticket)

        # Switch conversation mode to waiting_human / human
        conv = await self.conversation_repo.get_by_id(conversation_id)
        if conv:
            conv.mode = "waiting_human"
            await self.conversation_repo.save(conv)

        await self.audit_repo.log(
            actor_type="customer" if principal.is_authenticated_customer else "agent",
            actor_id=str(principal.customer_id or "agent"),
            action="ticket.created",
            subject_type="ticket",
            subject_id=str(ticket.id),
            before_state=None,
            after_state={"code": ticket.code, "reason": reason_code, "status": ticket.status},
        )

        await self.outbox_repo.add_event(
            event_type="ticket.created",
            payload={
                "ticket_id": str(ticket.id),
                "ticket_code": ticket.code,
                "conversation_id": str(conversation_id),
                "reason_code": reason_code,
            },
            idempotency_key=f"ticket_created_{ticket.id}",
        )

        return ticket

    async def claim_ticket(
        self,
        principal: Principal,
        ticket_id: uuid.UUID,
    ) -> TicketModel:
        """Staff claims an open ticket."""
        if not principal.is_staff:
            raise ForbiddenError("Chỉ nhân viên mới có quyền tiếp nhận phiếu hỗ trợ.")

        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise NotFoundError(f"Không tìm thấy phiếu hỗ trợ {ticket_id}.", error_code="TICKET_NOT_FOUND")

        if ticket.status not in ("open", "assigned"):
            raise ConflictError(f"Phiếu hỗ trợ đã ở trạng thái '{ticket.status}'.", error_code="TICKET_NOT_OPEN")

        prev_status = ticket.status
        ticket.status = "assigned"
        ticket.assignee = principal.user_id
        await self.ticket_repo.save(ticket)

        # Update conversation mode to human
        conv = await self.conversation_repo.get_by_id(ticket.conversation_id)
        if conv:
            conv.mode = "human"
            await self.conversation_repo.save(conv)

        await self.audit_repo.log(
            actor_type="staff",
            actor_id=str(principal.user_id),
            action="ticket.claimed",
            subject_type="ticket",
            subject_id=str(ticket.id),
            before_state={"status": prev_status},
            after_state={"status": ticket.status, "assignee": str(ticket.assignee)},
        )

        return ticket

    async def resolve_ticket(
        self,
        principal: Principal,
        ticket_id: uuid.UUID,
        resolution_notes: str,
    ) -> TicketModel:
        """Staff resolves ticket."""
        if not principal.is_staff:
            raise ForbiddenError("Chỉ nhân viên mới có quyền đóng phiếu hỗ trợ.")

        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if not ticket:
            raise NotFoundError(f"Không tìm thấy phiếu hỗ trợ {ticket_id}.", error_code="TICKET_NOT_FOUND")

        prev_status = ticket.status
        ticket.status = "resolved"
        ticket.context = {**(ticket.context or {}), "resolution_notes": resolution_notes}
        await self.ticket_repo.save(ticket)

        await self.audit_repo.log(
            actor_type="staff",
            actor_id=str(principal.user_id),
            action="ticket.resolved",
            subject_type="ticket",
            subject_id=str(ticket.id),
            before_state={"status": prev_status},
            after_state={"status": ticket.status, "notes": resolution_notes},
        )

        return ticket
