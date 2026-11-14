"""Background scheduler for periodic TTL expiration tasks."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopagent.core.clock import get_clock
from shopagent.domain.models.enums import ReturnStatus
from shopagent.domain.services.actions import ActionService
from shopagent.domain.state_machines import transition_return_status
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.tables import ReturnRequestModel

logger = logging.getLogger("shopagent.outbox.scheduler")


class BackgroundScheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = 60.0,
    ) -> None:
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self.clock = get_clock()
        self._running = False

    async def run_once(self) -> None:
        """Execute one cycle of cleanup tasks."""
        now = self.clock.now()

        async with self.session_factory() as session:
            # 1. Expire stale pending actions (> 30 min TTL)
            action_service = ActionService(session)
            expired_actions = await action_service.expire_stale_actions()
            if expired_actions > 0:
                logger.info("Expired %d stale pending actions.", expired_actions)

            # 2. Expire unreturned shipments (> deadline_ship_back)
            audit_repo = AuditRepository(session)
            outbox_repo = OutboxRepository(session)

            stmt = (
                select(ReturnRequestModel)
                .where(ReturnRequestModel.status == ReturnStatus.AWAITING_RETURN.value)
                .where(ReturnRequestModel.deadline_ship_back < now)
            )
            res = await session.execute(stmt)
            overdue_returns = list(res.scalars().all())

            for ret in overdue_returns:
                prev_status = ret.status
                transition_return_status(ret, ReturnStatus.EXPIRED.value)
                await audit_repo.log(
                    actor_type="system",
                    actor_id="scheduler",
                    action="return.expired",
                    subject_type="return_request",
                    subject_id=str(ret.id),
                    before_state={"status": prev_status},
                    after_state={"status": ret.status},
                )
                await outbox_repo.add_event(
                    event_type="return.expired",
                    payload={"return_id": str(ret.id), "return_code": ret.code},
                    idempotency_key=f"return_expired_{ret.id}",
                )

            if overdue_returns:
                logger.info("Expired %d overdue return requests past shipping deadline.", len(overdue_returns))

            await session.commit()

    async def start(self) -> None:
        """Main scheduler loop."""
        self._running = True
        logger.info("Background scheduler started.")
        while self._running:
            try:
                await self.run_once()
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler error: %s", e, exc_info=True)
                await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._running = False
