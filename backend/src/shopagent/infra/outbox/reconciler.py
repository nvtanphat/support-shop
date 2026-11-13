"""Reconciliation task for payment refunds and external state alignment."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shopagent.core.clock import get_clock
from shopagent.domain.models.enums import RefundStatus
from shopagent.infra.db.tables import RefundModel
from shopagent.infra.payments.port import PaymentGatewayPort
from shopagent.infra.payments.simulated import get_simulated_gateway

logger = logging.getLogger("shopagent.outbox.reconciler")


class PaymentReconciler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: PaymentGatewayPort | None = None,
        interval_seconds: float = 300.0,
    ) -> None:
        self.session_factory = session_factory
        self.gateway = gateway or get_simulated_gateway()
        self.interval_seconds = interval_seconds
        self.clock = get_clock()
        self._running = False

    async def run_once(self) -> int:
        """Query external gateway for pending/stuck processing refunds."""
        reconciled = 0
        async with self.session_factory() as session:
            stmt = select(RefundModel).where(RefundModel.status == RefundStatus.PROCESSING.value)
            res = await session.execute(stmt)
            processing_refunds = list(res.scalars().all())

            for ref in processing_refunds:
                if ref.gateway_txn_id:
                    result = await self.gateway.query_transaction(ref.gateway_txn_id)
                    if result.status == "succeeded":
                        ref.status = RefundStatus.SUCCEEDED.value
                        reconciled += 1
                    elif result.status == "failed":
                        ref.status = RefundStatus.FAILED.value
                        reconciled += 1

            if reconciled > 0:
                await session.commit()
                logger.info("Reconciled %d processing refunds.", reconciled)

        return reconciled

    async def start(self) -> None:
        self._running = True
        logger.info("Payment reconciler started.")
        while self._running:
            try:
                await self.run_once()
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Reconciler loop error: %s", e, exc_info=True)
                await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._running = False
