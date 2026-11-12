"""Support ticket repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.infra.db.tables import TicketModel


class TicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, ticket_id: uuid.UUID) -> TicketModel | None:
        stmt = select(TicketModel).where(TicketModel.id == ticket_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_code(self, code: str) -> TicketModel | None:
        stmt = select(TicketModel).where(TicketModel.code == code)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_open(self, limit: int = 50) -> list[TicketModel]:
        stmt = (
            select(TicketModel)
            .where(TicketModel.status.in_(["open", "assigned"]))
            .order_by(TicketModel.created_at.asc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, ticket: TicketModel) -> None:
        self.session.add(ticket)
        await self.session.flush()
