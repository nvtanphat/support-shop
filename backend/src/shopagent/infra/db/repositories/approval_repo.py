"""Approval request repository."""

from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.domain.models.enums import ApprovalStatus
from shopagent.infra.db.tables import ApprovalRequestModel


class ApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, approval_id: uuid.UUID) -> ApprovalRequestModel | None:
        stmt = select(ApprovalRequestModel).where(ApprovalRequestModel.id == approval_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_pending(self, required_role: str | None = None, limit: int = 50) -> list[ApprovalRequestModel]:
        stmt = (
            select(ApprovalRequestModel)
            .where(ApprovalRequestModel.status == ApprovalStatus.PENDING.value)
        )
        if required_role is not None:
            stmt = stmt.where(ApprovalRequestModel.required_role == required_role)
        stmt = stmt.order_by(ApprovalRequestModel.requested_at.asc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def has_pending_for_subject(self, subject_id: uuid.UUID) -> bool:
        stmt = (
            select(ApprovalRequestModel.id)
            .where(ApprovalRequestModel.subject_id == subject_id)
            .where(ApprovalRequestModel.status == ApprovalStatus.PENDING.value)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def save(self, approval: ApprovalRequestModel) -> None:
        self.session.add(approval)
        await self.session.flush()
