"""Audit log repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.core.ids import generate_uuid
from shopagent.infra.db.tables import AuditLogModel


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.clock = get_clock()

    async def log(
        self,
        actor_type: str,
        actor_id: str,
        action: str,
        subject_type: str,
        subject_id: str,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> AuditLogModel:
        entry = AuditLogModel(
            id=generate_uuid(),
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            before_state=before_state,
            after_state=after_state,
            request_id=request_id,
            at=self.clock.now(),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
