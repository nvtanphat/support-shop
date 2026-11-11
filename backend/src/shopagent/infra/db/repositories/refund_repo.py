"""Refund repository."""

from __future__ import annotations

import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.domain.models.enums import RefundStatus
from shopagent.infra.db.tables import RefundModel


class RefundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, refund_id: uuid.UUID) -> RefundModel | None:
        stmt = select(RefundModel).where(RefundModel.id == refund_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_code(self, code: str) -> RefundModel | None:
        stmt = select(RefundModel).where(RefundModel.code == code)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_order_id(self, order_id: uuid.UUID) -> list[RefundModel]:
        stmt = select(RefundModel).where(RefundModel.order_id == order_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_total_refunded_for_order(self, order_id: uuid.UUID) -> int:
        """Sum of succeeded and processing refunds for an order."""
        stmt = (
            select(func.coalesce(func.sum(RefundModel.amount), 0))
            .where(RefundModel.order_id == order_id)
            .where(RefundModel.status.in_([RefundStatus.PROCESSING.value, RefundStatus.SUCCEEDED.value]))
        )
        res = await self.session.execute(stmt)
        return int(res.scalar_one())

    async def save(self, refund: RefundModel) -> None:
        self.session.add(refund)
        await self.session.flush()
