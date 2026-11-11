"""Conversation, message, and event repository."""

from __future__ import annotations

import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shopagent.core.ids import generate_uuid
from shopagent.infra.db.tables import (
    ConversationEventModel,
    ConversationModel,
    MessageModel,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, conversation_id: uuid.UUID) -> ConversationModel | None:
        stmt = (
            select(ConversationModel)
            .options(selectinload(ConversationModel.messages))
            .where(ConversationModel.id == conversation_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create(
        self, customer_id: uuid.UUID | None = None, guest_token: str | None = None
    ) -> ConversationModel:
        conv = ConversationModel(
            id=generate_uuid(),
            customer_id=customer_id,
            guest_token=guest_token,
            mode="ai",
        )
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[str] | None = None,
        author_staff_id: uuid.UUID | None = None,
    ) -> MessageModel:
        # Determine next seq
        stmt = select(func.coalesce(func.max(MessageModel.seq), 0)).where(
            MessageModel.conversation_id == conversation_id
        )
        res = await self.session.execute(stmt)
        next_seq = int(res.scalar_one()) + 1

        msg = MessageModel(
            id=generate_uuid(),
            conversation_id=conversation_id,
            seq=next_seq,
            role=role,
            content=content,
            citations=citations or [],
            author_staff_id=author_staff_id,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def add_event(
        self, conversation_id: uuid.UUID, event_type: str, payload: dict
    ) -> ConversationEventModel:
        stmt = select(func.coalesce(func.max(ConversationEventModel.seq), 0)).where(
            ConversationEventModel.conversation_id == conversation_id
        )
        res = await self.session.execute(stmt)
        next_seq = int(res.scalar_one()) + 1

        event = ConversationEventModel(
            id=generate_uuid(),
            conversation_id=conversation_id,
            seq=next_seq,
            type=event_type,
            payload=payload,
        )
        self.session.add(event)

        # Update last_event_seq on conversation
        conv_stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
        conv_res = await self.session.execute(conv_stmt)
        conv = conv_res.scalar_one_or_none()
        if conv:
            conv.last_event_seq = next_seq

        await self.session.flush()
        return event

    async def get_events_since(
        self, conversation_id: uuid.UUID, since_seq: int = 0
    ) -> list[ConversationEventModel]:
        stmt = (
            select(ConversationEventModel)
            .where(ConversationEventModel.conversation_id == conversation_id)
            .where(ConversationEventModel.seq > since_seq)
            .order_by(ConversationEventModel.seq.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, conv: ConversationModel) -> None:
        self.session.add(conv)
        await self.session.flush()
