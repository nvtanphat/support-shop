"""Node 1: load_context - Fetch dynamic context for the turn."""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.state import AgentState
from shopagent.core.clock import get_clock
from shopagent.core.config import get_rules_config
from shopagent.infra.db.tables import CustomerModel, OrderModel, PendingActionModel


async def load_context_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Load dynamic facts (Principal, tier, pending actions, recent orders, clock)."""
    session = config.get("configurable", {}).get("session")
    if not session or not isinstance(session, AsyncSession):
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
        "policy_version": str(get_rules_config()["version"]),
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
            }

        # Active pending action in this conversation
        if conv_id:
            try:
                c_uuid = uuid.UUID(conv_id)
                stmt_act = (
                    select(PendingActionModel)
                    .where(
                        PendingActionModel.conversation_id == c_uuid,
                        PendingActionModel.status == "proposed",
                    )
                    .order_by(PendingActionModel.presented_at.desc())
                )
                res_act = await session.execute(stmt_act)
                acts = res_act.scalars().all()
                for act in acts:
                    act_exp = act.expires_at
                    clock_cmp = clock
                    if act_exp.tzinfo is not None and clock_cmp.tzinfo is None:
                        clock_cmp = clock_cmp.replace(tzinfo=act_exp.tzinfo)
                    elif act_exp.tzinfo is None and clock_cmp.tzinfo is not None:
                        act_exp = act_exp.replace(tzinfo=clock_cmp.tzinfo)

                    if act_exp > clock_cmp:
                        dynamic_context["active_pending_action"] = {
                            "action_id": str(act.id),
                            "code": str(act.id)[:8],
                            "type": act.type,
                            "preview": act.preview,
                            "preview_hash": act.payload_hash,
                            "expires_at": act.expires_at.isoformat(),
                        }
                        break
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
        "pending_action": dynamic_context.get("active_pending_action"),
        # Per-turn outputs are reset so nothing from the previous turn can leak into this one.
        "retrieved_clauses": [],
        "tool_calls": [],
        "turn_status": "incomplete",
        "unmet_requirements": [],
        "verified_output": None,
        "error": None,
    }
