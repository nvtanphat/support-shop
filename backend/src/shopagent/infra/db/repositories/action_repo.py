"""Pending action repository."""

from __future__ import annotations

from datetime import datetime
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.domain.models.enums import PendingActionStatus
from shopagent.infra.db.tables import PendingActionModel


class ActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, action_id: uuid.UUID) -> PendingActionModel | None:
        stmt = select(PendingActionModel).where(PendingActionModel.id == action_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_proposal(
        self, conversation_id: uuid.UUID, payload_hash: str
    ) -> PendingActionModel | None:
        stmt = (
            select(PendingActionModel)
            .where(PendingActionModel.conversation_id == conversation_id)
            .where(PendingActionModel.payload_hash == payload_hash)
            .where(PendingActionModel.status == PendingActionStatus.PROPOSED.value)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_any_active_proposal_for_conversation(
        self, conversation_id: uuid.UUID
    ) -> PendingActionModel | None:
        stmt = (
            select(PendingActionModel)
            .where(PendingActionModel.conversation_id == conversation_id)
            .where(PendingActionModel.status == PendingActionStatus.PROPOSED.value)
            .order_by(PendingActionModel.presented_at.desc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def save(self, action: PendingActionModel) -> None:
        self.session.add(action)
        await self.session.flush()
