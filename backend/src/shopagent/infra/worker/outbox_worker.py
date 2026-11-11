"""Outbox Worker for reliable, idempotent asynchronous event processing."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopagent.core.clock import get_clock
from shopagent.infra.db.tables import AuditLogModel, OutboxEventModel, RefundModel

logger = logging.getLogger(__name__)


async def process_outbox_batch(session: AsyncSession, limit: int = 10) -> int:
    """Process a single batch of pending outbox events idempotently."""
    now = get_clock().now()

    stmt = (
        select(OutboxEventModel)
        .where(
            OutboxEventModel.status == "pending",
            OutboxEventModel.next_attempt_at <= now,
        )
        .order_by(OutboxEventModel.created_at.asc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    events = result.scalars().all()

    processed_count = 0

    for event in events:
        event.attempts += 1
        try:
            if event.type == "refund.execute":
                refund_id_raw = event.payload.get("refund_id")
                if refund_id_raw:
                    refund_id = uuid.UUID(str(refund_id_raw))
                    stmt_ref = select(RefundModel).where(RefundModel.id == refund_id)
                    res_ref = await session.execute(stmt_ref)
                    refund = res_ref.scalar_one_or_none()

                    if refund and refund.status != "succeeded":
                        # Simulate payment gateway payout
                        refund.gateway_txn_id = f"GW-{uuid.uuid4().hex[:12].upper()}"
                        refund.status = "succeeded"

                        # Audit log entry
                        audit = AuditLogModel(
                            actor_type="system",
                            actor_id="outbox_worker",
                            action="refund.executed",
                            subject_type="refund",
                            subject_id=str(refund.id),
                            before_state={"status": "processing"},
                            after_state={
                                "status": "succeeded",
                                "gateway_txn_id": refund.gateway_txn_id,
                                "amount": refund.amount,
                            },
                            at=now,
                        )
                        session.add(audit)

            event.status = "processed"
            processed_count += 1
        except Exception as e:
            logger.error("Error processing outbox event %s: %s", event.id, e)
            if event.attempts >= 5:
                event.status = "failed"
            else:
                # Exponential backoff: 2, 4, 8, 16 seconds
                backoff_secs = 2 ** event.attempts
                event.next_attempt_at = now + timedelta(seconds=backoff_secs)

    await session.commit()
    return processed_count


async def run_outbox_worker(
    session_factory: async_sessionmaker[AsyncSession],
    poll_interval: float = 2.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run continuous outbox worker loop until stop_event is set."""
    logger.info("Starting Outbox Worker loop...")
    while stop_event is None or not stop_event.is_set():
        try:
            async with session_factory() as session:
                await process_outbox_batch(session)
        except Exception as e:
            logger.error("Outbox worker loop error: %s", e)

        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                break
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(poll_interval)
