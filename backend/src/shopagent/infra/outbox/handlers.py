"""Outbox event handlers.

All handlers must be idempotent (at-least-once delivery semantics).
"""

from __future__ import annotations

import logging
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.domain.models.enums import RefundStatus
from shopagent.domain.services.refunds import RefundService
from shopagent.infra.db.repositories.refund_repo import RefundRepository
from shopagent.infra.db.tables import OutboxEventModel
from shopagent.infra.payments.simulated import SimulatedPaymentGateway

logger = logging.getLogger("shopagent.outbox.handlers")


async def handle_refund_created(session: AsyncSession, event: OutboxEventModel) -> None:
    """Disburse refund if auto-approved (created status) and no approvals pending."""
    refund_id_str = event.payload.get("refund_id")
    if not refund_id_str:
        return

    refund_id = uuid.UUID(refund_id_str)
    refund_repo = RefundRepository(session)
    refund = await refund_repo.get_by_id(refund_id)
    if not refund:
        return

    # If created (not pending_approval), disburse automatically
    if refund.status == RefundStatus.CREATED.value:
        refund_service = RefundService(session)
        gateway = SimulatedPaymentGateway()
        await refund_service.process_disbursement(refund_id, gateway, actor_id="outbox_worker")


async def handle_approval_decided(session: AsyncSession, event: OutboxEventModel) -> None:
    """If a refund was approved, disburse it."""
    subject_type = event.payload.get("subject_type")
    decision = event.payload.get("decision")
    subject_id_str = event.payload.get("subject_id")

    if subject_type == "refund" and decision == "approved" and subject_id_str:
        refund_id = uuid.UUID(subject_id_str)
        refund_repo = RefundRepository(session)
        refund = await refund_repo.get_by_id(refund_id)
        if refund and refund.status == RefundStatus.APPROVED.value:
            refund_service = RefundService(session)
            gateway = SimulatedPaymentGateway()
            await refund_service.process_disbursement(refund_id, gateway, actor_id="outbox_worker")


async def handle_return_created(session: AsyncSession, event: OutboxEventModel) -> None:
    """Handle post-return creation tasks (e.g. shipping labels or customer notification)."""
    return_code = event.payload.get("return_code")
    logger.info("Return request %s created successfully.", return_code)


async def handle_action_confirmed(session: AsyncSession, event: OutboxEventModel) -> None:
    action_id = event.payload.get("action_id")
    logger.info("Action %s confirmed.", action_id)


HANDLERS = {
    "refund.created": handle_refund_created,
    "approval.decided": handle_approval_decided,
    "return.created": handle_return_created,
    "action.confirmed": handle_action_confirmed,
}
