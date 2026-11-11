"""LangGraph Agent adapter for the evaluation harness."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.graph import build_agent_graph
from shopagent.agent.state import AgentState
from shopagent.core.clock import get_clock
from shopagent.core.principal import Principal


class LangGraphAgent:
    """Evaluation harness adapter running the official 5-node LangGraph pipeline."""

    def __init__(
        self,
        session: AsyncSession,
        principal: Principal,
        clock: datetime | None = None,
    ) -> None:
        self.session = session
        self.principal = principal
        self.clock = clock or get_clock().now()
        self.graph = build_agent_graph()

    async def step(
        self,
        conversation_id: str,
        user_message: str,
        dialogue_history: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        """Execute one turn through the 5-node LangGraph agent graph."""
        # In LangGraph with checkpointer, only pass the NEW message for the turn.
        # History is automatically managed by the checkpointer for thread_id.
        messages: list[BaseMessage] = [HumanMessage(content=user_message)]

        state: AgentState = {
            "conversation_id": conversation_id,
            "messages": messages,
            "principal": self.principal,
            "clock": self.clock,
        }

        config = {
            "configurable": {
                "thread_id": conversation_id,
                "session": self.session,
            }
        }

        output = await self.graph.ainvoke(state, config=config)

        asst_text = output.get("verified_output") or ""
        tool_calls = output.get("tool_calls") or []
        pending_action = output.get("pending_action")

        if pending_action:
            act_id = pending_action.get("action_id") or pending_action.get("id")
            pending_action = {
                "id": str(act_id),
                "action_id": str(act_id),
                "type": pending_action.get("type"),
                "preview_hash": pending_action.get("preview_hash"),
                "preview": pending_action.get("preview"),
            }

        return asst_text, tool_calls, pending_action
