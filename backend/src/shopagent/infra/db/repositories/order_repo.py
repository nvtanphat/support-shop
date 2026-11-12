"""Order repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shopagent.domain.models.enums import OrderStatus
from shopagent.infra.db.tables import OrderItemModel, OrderModel, ProductVariantModel


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, order_id: uuid.UUID) -> OrderModel | None:
        stmt = (
            select(OrderModel)
            .options(
                selectinload(OrderModel.items).selectinload(OrderItemModel.variant).selectinload(ProductVariantModel.product),
                selectinload(OrderModel.returns),
                selectinload(OrderModel.refunds),
            )
            .where(OrderModel.id == order_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_code(self, code: str) -> OrderModel | None:
        stmt = (
            select(OrderModel)
            .options(
                selectinload(OrderModel.items).selectinload(OrderItemModel.variant).selectinload(ProductVariantModel.product),
                selectinload(OrderModel.returns),
                selectinload(OrderModel.refunds),
            )
            .where(OrderModel.code == code)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_customer(
        self, customer_id: uuid.UUID, status: OrderStatus | None = None, limit: int = 5
    ) -> list[OrderModel]:
        stmt = (
            select(OrderModel)
            .options(
                selectinload(OrderModel.items).selectinload(OrderItemModel.variant)
            )
            .where(OrderModel.customer_id == customer_id)
        )
        if status is not None:
            stmt = stmt.where(OrderModel.status == status.value)
        stmt = stmt.order_by(OrderModel.placed_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, order: OrderModel) -> None:
        self.session.add(order)
        await self.session.flush()
