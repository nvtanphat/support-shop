"""LangGraph Agent adapter for the evaluation harness."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from shopagent.agent.graph import build_agent_graph
from shopagent.agent.state import AgentState
from shopagent.core.clock import get_clock
from shopagent.core.principal import Principal
from sqlalchemy.ext.asyncio import AsyncSession


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
        # Evaluation conversations live in memory: they must not pollute the application's checkpoint store.
        self.usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0}
        self._counted_ids: set[str] = set()
        self.last_verification_error: str | None = None
        self.graph = build_agent_graph(checkpointer=InMemorySaver())

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

        self._count_usage(output.get("messages") or [])
        # Why verify_output replaced the model's answer, if it did (kept for failure analysis).
        self.last_verification_error = output.get("error")
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

    def _count_usage(self, messages: list[BaseMessage]) -> None:
        """Add token usage of AI messages not seen before (state carries the whole history)."""
        for msg in messages:
            msg_id = getattr(msg, "id", None)
            usage = getattr(msg, "usage_metadata", None)
            if not usage or not msg_id or msg_id in self._counted_ids:
                continue
            self._counted_ids.add(msg_id)
            self.usage["llm_calls"] += 1
            self.usage["input_tokens"] += int(usage.get("input_tokens", 0))
            self.usage["output_tokens"] += int(usage.get("output_tokens", 0))
