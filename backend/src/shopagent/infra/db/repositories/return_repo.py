"""Return request repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shopagent.infra.db.tables import ReturnItemModel, ReturnRequestModel


class ReturnRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, return_id: uuid.UUID) -> ReturnRequestModel | None:
        stmt = (
            select(ReturnRequestModel)
            .options(
                selectinload(ReturnRequestModel.items).selectinload(ReturnItemModel.order_item),
                selectinload(ReturnRequestModel.evidence_files),
                selectinload(ReturnRequestModel.order),
            )
            .where(ReturnRequestModel.id == return_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_code(self, code: str) -> ReturnRequestModel | None:
        stmt = (
            select(ReturnRequestModel)
            .options(
                selectinload(ReturnRequestModel.items).selectinload(ReturnItemModel.order_item),
                selectinload(ReturnRequestModel.evidence_files),
                selectinload(ReturnRequestModel.order),
            )
            .where(ReturnRequestModel.code == code)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_customer(self, customer_id: uuid.UUID, limit: int = 10) -> list[ReturnRequestModel]:
        stmt = (
            select(ReturnRequestModel)
            .options(selectinload(ReturnRequestModel.items))
            .where(ReturnRequestModel.customer_id == customer_id)
            .order_by(ReturnRequestModel.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, return_req: ReturnRequestModel) -> None:
        self.session.add(return_req)
        await self.session.flush()
