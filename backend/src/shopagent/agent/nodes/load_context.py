"""Node 1: load_context - Fetch dynamic context for the turn."""

from __future__ import annotations

from typing import Any
import uuid
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shopagent.agent.state import AgentState
from shopagent.core.clock import get_clock
from shopagent.infra.db.tables import CustomerModel, OrderModel, PendingActionModel


async def load_context_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Load dynamic facts (Principal, tier, pending actions, recent orders, clock)."""
    session: AsyncSession = config.get("configurable", {}).get("session")
    if not session:
        raise ValueError("AsyncSession must be provided in config['configurable']['session']")
    principal = state.get("principal")
    clock = state.get("clock") or get_clock().now()
    conv_id = state.get("conversation_id")

    dynamic_context: dict[str, Any] = {
        "clock_iso": clock.isoformat(),
        "role": principal.role.value if principal else "guest",
        "customer": None,
        "active_pending_action": None,
        "recent_orders": [],
        "policy_version": "2026-11-01",
    }

    if principal and principal.is_authenticated_customer and principal.customer_id:
        stmt = select(CustomerModel).where(CustomerModel.id == principal.customer_id)
        res = await session.execute(stmt)
        cust = res.scalar_one_or_none()
        if cust:
            dynamic_context["customer"] = {
                "id": str(cust.id),
                "full_name": cust.full_name,
                "tier": cust.tier,
                "email": cust.email,
            }

        # Active pending action in this conversation
        if conv_id:
            try:
                c_uuid = uuid.UUID(conv_id)
                stmt_act = select(PendingActionModel).where(
                    PendingActionModel.conversation_id == c_uuid,
                    PendingActionModel.status == "proposed",
                )
                res_act = await session.execute(stmt_act)
                act = res_act.scalar_one_or_none()
                if act and act.expires_at > clock:
                    dynamic_context["active_pending_action"] = {
                        "action_id": str(act.id),
                        "type": act.type,
                        "preview": act.preview,
                        "preview_hash": act.payload_hash,
                    }
            except Exception:
                pass

        # Recent orders
        stmt_orders = (
            select(OrderModel)
            .where(OrderModel.customer_id == principal.customer_id)
            .order_by(OrderModel.placed_at.desc())
            .limit(3)
        )
        res_orders = await session.execute(stmt_orders)
        orders = res_orders.scalars().all()
        dynamic_context["recent_orders"] = [
            {"code": o.code, "status": o.status, "total": o.total, "placed_at": o.placed_at.isoformat()}
            for o in orders
        ]

    return {
        "dynamic_context": dynamic_context,
        "clock": clock,
    }
