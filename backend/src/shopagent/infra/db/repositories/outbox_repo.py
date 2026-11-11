"""Outbox repository using FOR UPDATE SKIP LOCKED for worker queueing."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.core.ids import generate_uuid
from shopagent.domain.models.enums import OutboxStatus
from shopagent.infra.db.tables import OutboxEventModel


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.clock = get_clock()

    async def add_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        next_attempt_at: datetime | None = None,
    ) -> OutboxEventModel:
        now = self.clock.now()
        event = OutboxEventModel(
            id=generate_uuid(),
            type=event_type,
            payload=payload,
            status=OutboxStatus.PENDING.value,
            idempotency_key=idempotency_key,
            next_attempt_at=next_attempt_at or now,
            created_at=now,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def fetch_pending_batch(
        self, now: datetime, limit: int = 10
    ) -> list[OutboxEventModel]:
        """Fetch pending outbox events ready for processing using FOR UPDATE SKIP LOCKED.

        Ensures multiple workers do not process the same event concurrently.
        """
        stmt = (
            select(OutboxEventModel)
            .where(OutboxEventModel.status == OutboxStatus.PENDING.value)
            .where(OutboxEventModel.next_attempt_at <= now)
            .order_by(OutboxEventModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def mark_published(self, event_id: uuid.UUID) -> None:
        stmt = select(OutboxEventModel).where(OutboxEventModel.id == event_id)
        res = await self.session.execute(stmt)
        event = res.scalar_one_or_none()
        if event:
            event.status = OutboxStatus.PUBLISHED.value
            await self.session.flush()

    async def mark_failed(self, event_id: uuid.UUID, next_attempt_at: datetime, max_attempts: int = 5) -> None:
        stmt = select(OutboxEventModel).where(OutboxEventModel.id == event_id)
        res = await self.session.execute(stmt)
        event = res.scalar_one_or_none()
        if event:
            event.attempts += 1
            if event.attempts >= max_attempts:
                event.status = OutboxStatus.FAILED.value
            else:
                event.next_attempt_at = next_attempt_at
            await self.session.flush()
