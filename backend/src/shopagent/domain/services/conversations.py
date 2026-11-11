"""Conversation management domain service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.core.errors import ForbiddenError, NotFoundError, ValidationError
from shopagent.core.principal import Principal, PrincipalRole
from shopagent.domain.state_machines import transition_conversation_mode
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.conversation_repo import ConversationRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.tables import (
    ConversationEventModel,
    ConversationModel,
    MessageModel,
)


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversation_repo = ConversationRepository(session)
        self.audit_repo = AuditRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.clock = get_clock()

    async def get_or_create(
        self,
        customer_id: uuid.UUID | None = None,
        guest_token: str | None = None,
    ) -> ConversationModel:
        """Create a new customer conversation."""
        return await self.conversation_repo.create(
            customer_id=customer_id,
            guest_token=guest_token,
        )

    async def get_conversation(
        self,
        conversation_id: uuid.UUID,
        principal: Principal,
    ) -> ConversationModel:
        """Get conversation with ownership check."""
        conv = await self.conversation_repo.get_by_id(conversation_id)
        if not conv:
            raise NotFoundError(f"Không tìm thấy hội thoại {conversation_id}.", error_code="CONVERSATION_NOT_FOUND")

        # Access check
        if principal.is_authenticated_customer:
            if conv.customer_id != principal.customer_id:
                raise ForbiddenError("Bạn không có quyền truy cập hội thoại này.", error_code="CONVERSATION_ACCESS_DENIED")
        elif principal.is_guest:
            if conv.guest_token != principal.guest_token:
                raise ForbiddenError("Bạn không có quyền truy cập hội thoại này.", error_code="CONVERSATION_ACCESS_DENIED")
        elif not principal.is_staff and principal.role != PrincipalRole.SYSTEM:
            raise ForbiddenError("Quyền truy cập bị từ chối.", error_code="CONVERSATION_ACCESS_DENIED")

        return conv

    async def append_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[str] | None = None,
        author_staff_id: uuid.UUID | None = None,
    ) -> MessageModel:
        """Append message and record durable event."""
        msg = await self.conversation_repo.add_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations=citations,
            author_staff_id=author_staff_id,
        )

        # Durable conversation event
        await self.conversation_repo.add_event(
            conversation_id=conversation_id,
            event_type="message.completed",
            payload={
                "message_id": str(msg.id),
                "seq": msg.seq,
                "role": msg.role,
                "content": msg.content,
                "citations": msg.citations,
                "created_at": msg.created_at.isoformat(),
            },
        )

        return msg

    async def switch_mode(
        self,
        conversation_id: uuid.UUID,
        target_mode: str,
        principal: Principal,
    ) -> ConversationModel:
        """Switch conversation mode enforcing state machine."""
        conv = await self.get_conversation(conversation_id, principal)
        prev_mode = conv.mode

        transition_conversation_mode(conv, target_mode)
        conv.updated_at = self.clock.now()
        await self.conversation_repo.save(conv)

        # Durable event
        await self.conversation_repo.add_event(
            conversation_id=conversation_id,
            event_type="conversation.mode_changed",
            payload={"prev_mode": prev_mode, "new_mode": conv.mode},
        )

        await self.audit_repo.log(
            actor_type="staff" if principal.is_staff else "customer",
            actor_id=str(principal.user_id or principal.customer_id or "system"),
            action="conversation.mode_changed",
            subject_type="conversation",
            subject_id=str(conv.id),
            before_state={"mode": prev_mode},
            after_state={"mode": conv.mode},
        )

        return conv
