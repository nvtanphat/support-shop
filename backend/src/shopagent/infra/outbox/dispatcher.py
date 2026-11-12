"""Outbox dispatcher running batch polling with FOR UPDATE SKIP LOCKED."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopagent.core.clock import get_clock
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.outbox.handlers import HANDLERS

logger = logging.getLogger("shopagent.outbox.dispatcher")


class OutboxDispatcher:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        batch_size: int = 10,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.session_factory = session_factory
        self.batch_size = batch_size
        self.poll_interval_seconds = poll_interval_seconds
        self.clock = get_clock()
        self._running = False

    async def run_once(self) -> int:
        """Process one batch of pending outbox events. Returns count processed."""
        now = self.clock.now()
        processed_count = 0

        async with self.session_factory() as session:
            outbox_repo = OutboxRepository(session)
            events = await outbox_repo.fetch_pending_batch(now=now, limit=self.batch_size)
            if not events:
                return 0

            for event in events:
                handler = HANDLERS.get(event.type)
                if not handler:
                    # No registered handler; mark published to drain queue
                    await outbox_repo.mark_published(event.id)
                    processed_count += 1
                    continue

                try:
                    await handler(session, event)
                    await outbox_repo.mark_published(event.id)
                    processed_count += 1
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    logger.error(
                        "Error processing outbox event %s (%s): %s",
                        event.id,
                        event.type,
                        exc,
                        exc_info=True,
                    )
                    # Exponential backoff: 2^(attempts) * 5 seconds
                    backoff_seconds = (2 ** min(event.attempts, 6)) * 5
                    next_attempt = now + timedelta(seconds=backoff_seconds)
                    async with self.session_factory() as fail_session:
                        fail_repo = OutboxRepository(fail_session)
                        await fail_repo.mark_failed(
                            event.id,
                            next_attempt_at=next_attempt,
                            max_attempts=5,
                        )
                        await fail_session.commit()

        return processed_count

    async def start(self) -> None:
        """Main dispatcher polling loop."""
        self._running = True
        logger.info("Outbox dispatcher started.")
        while self._running:
            try:
                processed = await self.run_once()
                if processed == 0:
                    await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Outbox loop exception: %s", e, exc_info=True)
                await asyncio.sleep(self.poll_interval_seconds)

    def stop(self) -> None:
        self._running = False
